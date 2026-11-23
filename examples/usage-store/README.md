# The usage store

Where a team's usage bundles and heartbeats go, and the interface for reading them
([SPEC-004](../../docs/specs/004-usage-export/SPEC.md)). It runs in one of two places, with the same
queries, dashboards and alert rules in both:

| | Local | Cloud |
|---|---|---|
| The store | A folder on your machine | A bucket in your own cloud account |
| Who sorts what lands | `python3 validator.py --folder <folder>`, run by you | The same file, as the function the bucket calls |
| Grafana | A container on `127.0.0.1` only, from [`local/compose.yaml`](local/compose.yaml) | A container behind your identity provider's sign-in, from [`cloud/`](cloud/) |
| Detailed bundles | The owner's own data source and dashboard | Not readable by the team's Grafana at all: the owner reads them from a copy of the bucket, locally |

Nothing here names a store, an account or a person. Senders point at a store from their own gitignored
`.sanvio/export.json`, as [`reports/usage/README.md`](../../reports/usage/README.md) says.

## What's in it

| Path | What it is |
|---|---|
| [`queries/`](queries/) | The one copy of the SQL. `views.sql` reads `accepted/`, `views-detailed.sql` the detailed bundles, `rq-1.sql` to `rq-7.sql` answer the spec's seven questions, the `alert-*.sql` files feed the alert rules, and `lock.sql`, last in every data source, limits DuckDB to the store. `${USAGE_ROOT}` is the folder or bucket |
| [`validator.py`](validator.py) | Moves each object from `incoming/` to `accepted/` or `rejected/`, checked against [`scripts/usage_shape.py`](../../scripts/usage_shape.py), and marks a chain that changed between sends. On a folder it also removes what's older than 90 days, as the bucket's lifecycle does in the cloud |
| [`render.py`](render.py) | Writes Grafana's provisioning files from [`queries/`](queries/). Run it after changing a query; `--check` says if any is stale, and the tests run it |
| [`grafana/`](grafana/) | What [`render.py`](render.py) writes: the data sources, the dashboards and the alert rules |
| [`Dockerfile`](Dockerfile) | Grafana 13 with the DuckDB data source, both pinned, for the local and cloud forms alike |
| [`local/`](local/) | Running it on your machine |
| [`cloud/`](cloud/) | Running it in your own account, as Terraform |

## The questions

| Panel | Question |
|---|---|
| RQ-1 | Which skills, agents and slash commands did the team use, and which went unused? |
| RQ-2 | What does a pull request cost, by project and by agent? |
| RQ-3 | How many fix rounds does an issue take, by agent, reviewer and factory version? |
| RQ-4 | Where does the guard refuse or ask most, and which asks do people always say yes to? |
| RQ-5 | Is every node's loop running, and when did each last report? |
| RQ-6 | Which shell commands do agents run most, and which get refused or asked about? (detailed, owner only) |
| RQ-7 | What does an issue that reached a pull request cost all in, counting every run on it, and how much spend sits on issues with no pull request yet, by project? A pull request the loop opened, not one that merged |

Three alert rules come with it: a node whose last heartbeat is over 30 minutes old, a loop that stopped on
a machine still sending heartbeats, and a run past 80% of its token budget. Each node's or run's alert goes once to the webhook in `USAGE_ALERT_WEBHOOK`, once more
when it recovers, and not again while it stays down.

## Checking the SQL

The tests run each query over a folder of invented bundles with the DuckDB the plugin carries:

```
uv run --no-project --with duckdb==1.5.6 --with pytz python3 -m unittest tests.test_usage_store
```

Without DuckDB those tests skip, and the validator's still run.
