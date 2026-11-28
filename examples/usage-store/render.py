#!/usr/bin/env python3
"""Write Grafana's provisioning files from the SQL in queries/ (SPEC-004 REQ-022).

    python3 examples/usage-store/render.py           # write them
    python3 examples/usage-store/render.py --check   # change nothing, exit 1 if any is out of date

The SQL files are the one copy: the data sources' init SQL is views.sql (and views-detailed.sql for the
owner's), each dashboard panel's query is an rq-N.sql or an activity-*.sql, and each alert rule's query is an alert-*.sql. This
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
TABLE, SERIES = 1, 0  # the plugin's query formats: a time series turns long rows into a series per label

PANELS = [
    ("rq-1.sql", "RQ-1 Skills, agents and commands used", GENERAL),
    ("rq-2.sql", "RQ-2 Cost of a pull request, by project and agent", GENERAL),
    ("rq-3.sql", "RQ-3 Fix rounds by agent, reviewer and factory version", GENERAL),
    ("rq-4.sql", "RQ-4 Guard refusals and asks", GENERAL),
    ("rq-5.sql", "RQ-5 Nodes and their loops", GENERAL),
    ("rq-7.sql", "RQ-7 All-in cost of an issue that reached a pull request, by project", GENERAL),
]
DETAILED_PANELS = [("rq-6.sql", "RQ-6 Shell commands agents ran", DETAILED)]

# The activity dashboard: when the loop works, as bar charts. Each is (query file, title, panel type, query
# format, stacked bars, x, y, width, height, extra panel settings). The loop writes a run's start in its
# node's own clock with no time zone, so the dashboard shows times in UTC, which leaves them as written.
ACTIVITY_PANELS = [
    ("activity-runs-per-hour.sql", "Loop runs started each hour", "timeseries", TABLE, False, 0, 0, 24, 9, {}),
    ("activity-hour-of-day.sql", "Average loop runs by hour of day, on each node's clock", "barchart", TABLE,
     False, 0, 9, 14, 9, {}),
    ("activity-tokens-per-day.sql", "Tokens each day, by node", "timeseries", SERIES, True, 14, 9, 10, 9, {}),
    ("activity-last-week.sql", "Last 7 days, loop runs each hour by node", "timeseries", SERIES, True, 0, 18,
     24, 8, {"timeFrom": "7d"}),
]
ACTIVITY_NOTE = "Times are each node's own clock, as the loop wrote them."

ALERTS = [
    ("alert-silent-node.sql", "usage-silent-node", "A node stopped sending heartbeats", "minutes_silent", 30),
    ("alert-budget.sql", "usage-budget", "A run passed 80% of its token budget", "percent_of_budget", 80),
    ("alert-dead-loop.sql", "usage-dead-loop", "A loop died while its machine still reports", "stopped", 0),
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


def target(name, ds, fmt):
    return {"refId": "A", "datasource": {"type": PLUGIN, "uid": ds}, "rawSql": sql(name), "format": fmt,
            "editorMode": "code", "rawQuery": True}


def activity():
    out = []
    for i, (name, title, kind, fmt, stacked, x, y, w, h, extra) in enumerate(ACTIVITY_PANELS):
        panel = {"id": i + 1, "type": kind, "title": title, "description": ACTIVITY_NOTE,
                 "gridPos": {"h": h, "w": w, "x": x, "y": y}, "datasource": {"type": PLUGIN, "uid": GENERAL},
                 "targets": [target(name, GENERAL, fmt)]}
        if kind == "barchart":
            panel["fieldConfig"] = {"defaults": {"unit": "short", "decimals": 1}, "overrides": []}
            panel["options"] = {"xField": "hour", "orientation": "vertical", "showValue": "never",
                                "groupWidth": 0.8, "barWidth": 0.9,
                                "legend": {"showLegend": True, "placement": "bottom"}}
        else:
            panel["fieldConfig"] = {"defaults": {"unit": "short", "custom": {
                "drawStyle": "bars", "fillOpacity": 80, "lineWidth": 1, "barAlignment": 0, "showPoints": "never",
                "stacking": {"mode": "normal" if stacked else "none", "group": "A"}}}, "overrides": []}
            if fmt == SERIES:  # name each series by its node alone, not "tokens {node=...}"
                panel["fieldConfig"]["overrides"] = [{"matcher": {"id": "byType", "options": "number"},
                                                      "properties": [{"id": "displayName",
                                                                      "value": "${__field.labels.node}"}]}]
            panel["options"] = {"legend": {"showLegend": fmt == SERIES, "placement": "bottom"},
                                "tooltip": {"mode": "multi" if fmt == SERIES else "single"}}
        panel.update(extra)
        out.append(panel)
    return json.dumps({"uid": "factory-activity", "title": "Factory activity", "editable": False,
                       "schemaVersion": 39, "timezone": "utc", "time": {"from": "now-90d", "to": "now"},
                       "panels": out, "tags": ["sanvio-factory", "usage"]}, indent=2) + "\n"


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
        GRAFANA / "dashboards" / "activity.json": activity(),
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
