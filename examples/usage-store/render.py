#!/usr/bin/env python3
"""Write Grafana's provisioning files from the SQL in queries/ (SPEC-004 REQ-022).

    python3 examples/usage-store/render.py           # write them
    python3 examples/usage-store/render.py --check   # change nothing, exit 1 if any is out of date

The SQL files are the one copy: the data sources' init SQL is views.sql (and views-detailed.sql for the
owner's), each dashboard panel's query is an rq-N.sql, and each alert rule's query is an alert-*.sql. This
writes them into the files Grafana reads at start, so a fresh Grafana comes up with all of them, and
tests/test_usage_store.py fails when one is stale.

${USAGE_ROOT} and ${USAGE_INIT} stay as they are: Grafana fills them from its environment when it reads the
files, the folder or bucket the store is in, and the SQL a bucket needs first. Nothing here names a store.
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUERIES = HERE / "queries"
GRAFANA = HERE / "grafana"
PLUGIN = "motherduck-duckdb-datasource"
GENERAL, DETAILED = "usage", "usage-detailed"
TABLE = 1  # the plugin's query format, a number: 0 is a time series, 1 a table

PANELS = [
    ("rq-1.sql", "RQ-1 Skills, agents and commands used", GENERAL),
    ("rq-2.sql", "RQ-2 Cost of a pull request, by project and agent", GENERAL),
    ("rq-3.sql", "RQ-3 Fix rounds by agent, reviewer and factory version", GENERAL),
    ("rq-4.sql", "RQ-4 Guard refusals and asks", GENERAL),
    ("rq-5.sql", "RQ-5 Nodes and their loops", GENERAL),
    ("rq-7.sql", "RQ-7 All-in cost of an issue that reached a pull request, by project", GENERAL),
]
DETAILED_PANELS = [("rq-6.sql", "RQ-6 Shell commands agents ran", DETAILED)]

ALERTS = [
    ("alert-silent-node.sql", "usage-silent-node", "A node stopped sending heartbeats", "minutes_silent", 30),
    ("alert-budget.sql", "usage-budget", "A run passed 80% of its token budget", "percent_of_budget", 80),
    ("alert-dead-loop.sql", "usage-dead-loop", "A loop stopped while its machine still reports", "stopped", 0),
]


def sql(name):
    return (QUERIES / name).read_text(encoding="utf-8").strip()


def quoted(text, indent):
    """A YAML block scalar of text, indented."""
    pad = " " * indent
    return "|\n" + "\n".join(pad + line if line else "" for line in text.splitlines())


def datasource(uid, name, files, default):
    init = "${USAGE_INIT}\n" + "\n\n".join(sql(f) for f in list(files) + ["lock.sql"])
    return ("apiVersion: 1\n\ndatasources:\n"
            "  - name: {}\n    uid: {}\n    type: {}\n    access: proxy\n    isDefault: {}\n    editable: false\n"
            "    jsonData:\n      path: ''\n      initSql: {}\n").format(name, uid, PLUGIN, "true" if default else "false",
                                                                     quoted(init, 8))


def dashboard(uid, title, panels):
    out = []
    for i, (name, panel_title, ds) in enumerate(panels):
        out.append({"id": i + 1, "type": "table", "title": panel_title,
                    "gridPos": {"h": 9, "w": 12, "x": (i % 2) * 12, "y": (i // 2) * 9},
                    "datasource": {"type": PLUGIN, "uid": ds},
                    "targets": [{"refId": "A", "datasource": {"type": PLUGIN, "uid": ds}, "rawSql": sql(name),
                                 "format": TABLE, "editorMode": "code", "rawQuery": True}]})
    return json.dumps({"uid": uid, "title": title, "editable": False, "schemaVersion": 39, "time":
                       {"from": "now-30d", "to": "now"}, "panels": out, "tags": ["sanvio-factory", "usage"]},
                      indent=2) + "\n"


def rules():
    lines = ["apiVersion: 1", "", "groups:", "  - orgId: 1", "    name: usage", "    folder: Factory usage",
             "    interval: 1m", "    rules:"]
    for name, uid, title, column, threshold in ALERTS:
        lines += [
            "      - uid: {}".format(uid), "        title: {}".format(title), "        condition: C",
            "        for: 0s", "        noDataState: OK", "        execErrState: Error",
            "        annotations:", "          summary: {} ({} over {})".format(title, column, threshold),
            "        data:",
            "          - refId: A", "            datasourceUid: {}".format(GENERAL),
            "            relativeTimeRange: {from: 600, to: 0}", "            model:",
            "              refId: A", "              format: {}".format(TABLE), "              rawQuery: true",
            "              editorMode: code", "              rawSql: " + quoted(sql(name), 16),
            "          - refId: B", "            datasourceUid: __expr__", "            model:",
            "              refId: B", "              type: reduce", "              expression: A",
            "              reducer: last",
            "          - refId: C", "            datasourceUid: __expr__", "            model:",
            "              refId: C", "              type: threshold", "              expression: B",
            "              conditions:", "                - evaluator: {{type: gt, params: [{}]}}".format(threshold),
        ]
    return "\n".join(lines) + "\n"


CONTACT = """apiVersion: 1

# Where alerts go: a webhook whose address Grafana reads from USAGE_ALERT_WEBHOOK in its environment, never
# from this file. In the cloud the task reads it from the secret store by name. Each node's or run's alert is
# its own notification (group_by '...'), sent once, then once more when it resolves, and not again while it
# stays firing (REQ-015): repeat_interval is a year.
contactPoints:
  - orgId: 1
    name: usage-alerts
    receivers:
      - uid: usage-webhook
        type: webhook
        settings:
          url: ${USAGE_ALERT_WEBHOOK}
          httpMethod: POST

policies:
  - orgId: 1
    receiver: usage-alerts
    group_by: ['...']
    group_wait: 0s
    group_interval: 1m
    repeat_interval: 8760h
"""

DASHBOARD_PROVIDER = """apiVersion: 1

providers:
  - name: {name}
    folder: Factory usage
    type: file
    disableDeletion: true
    allowUiUpdates: false
    options:
      path: {path}
"""


def files():
    """Every file this writes, by path, with what it should hold."""
    return {
        GRAFANA / "provisioning" / "datasources" / "usage.yaml": datasource(GENERAL, "Usage", ["views.sql"], True),
        GRAFANA / "provisioning" / "dashboards" / "usage.yaml": DASHBOARD_PROVIDER.format(name="usage", path="/etc/grafana/dashboards"),
        GRAFANA / "provisioning" / "alerting" / "rules.yaml": rules(),
        GRAFANA / "provisioning" / "alerting" / "contact.yaml": CONTACT,
        GRAFANA / "dashboards" / "usage.json": dashboard("factory-usage", "Factory usage", PANELS),
        GRAFANA / "local" / "datasources" / "detailed.yaml":
            datasource(DETAILED, "Usage, detailed", ["views.sql", "views-detailed.sql"], False),
        GRAFANA / "local" / "dashboards" / "usage.yaml": DASHBOARD_PROVIDER.format(name="usage-detailed", path="/etc/grafana/local-dashboards"),
        GRAFANA / "local" / "dashboards" / "detailed.json":
            dashboard("factory-usage-detailed", "Factory usage, detailed", DETAILED_PANELS),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="change nothing; exit 1 if any file is stale")
    args = parser.parse_args(argv)
    stale = []
    for path, text in files().items():
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current == text:
            continue
        stale.append(path)
        if not args.check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    for path in stale:
        print(("stale: " if args.check else "wrote: ") + str(path.relative_to(HERE)))
    return 1 if args.check and stale else 0


if __name__ == "__main__":
    sys.exit(main())
