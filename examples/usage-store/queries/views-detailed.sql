-- Detailed bundles' commands (SPEC-004 REQ-014). Only the owner's data source loads this file: in the cloud,
-- the team's Grafana has no access to detailed/ or its key, and the owner reads it from a copy of the bucket.
-- One row per command, from each detailed bundle's latest export.

CREATE OR REPLACE VIEW commands AS
SELECT node, "user", c.* FROM (
    SELECT node, "user", unnest(commands) AS c FROM (
        SELECT *, row_number() OVER (PARTITION BY bundle_id ORDER BY exported DESC, filename DESC) AS newest
        FROM read_json('${USAGE_ROOT}/accepted/*/*/detailed/*.json', filename = true, ignore_errors = true, columns = {
            'kind': 'VARCHAR', 'exported': 'DATE', 'user': 'VARCHAR', 'node': 'VARCHAR', 'bundle_id': 'VARCHAR',
            'commands': 'STRUCT(ts TIMESTAMPTZ, "session" VARCHAR, verdict VARCHAR, "text" VARCHAR, redactions INTEGER)[]'
        })
        WHERE kind = 'bundle'
    ) WHERE newest = 1
);
