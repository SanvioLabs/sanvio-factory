-- The views every RQ query reads (SPEC-004 REQ-022). ${USAGE_ROOT} is the store's root: a folder such as
-- /store, or s3://<bucket>/<prefix>. Only accepted/ is read, and the _shape/ files the validator writes are
-- left out: they're there so an empty store reads as no rows rather than an error. Detailed bundles are in
-- views-detailed.sql, which only the owner's data source loads.

CREATE OR REPLACE VIEW bundle_files AS
SELECT * FROM read_json('${USAGE_ROOT}/accepted/*/*/general/*.json', filename = true, ignore_errors = true, columns = {
    'v': 'INTEGER', 'kind': 'VARCHAR', 'mode': 'VARCHAR', 'exported': 'DATE', 'since': 'DATE',
    'period': 'STRUCT("first" DATE, "last" DATE)', 'user': 'VARCHAR', 'node': 'VARCHAR',
    'factory': 'STRUCT("commit" VARCHAR, changelog VARCHAR)',
    'loop_config': 'MAP(VARCHAR, STRUCT(agent VARCHAR, reviewer VARCHAR, max_workers INTEGER, max_rounds INTEGER, max_issue_tokens BIGINT))',
    'chain_head': 'VARCHAR', 'bundle_id': 'VARCHAR',
    'loop': 'STRUCT(v INTEGER, run VARCHAR, issue BIGINT, project VARCHAR, started VARCHAR, ended VARCHAR, outcome VARCHAR, rounds INTEGER, tests VARCHAR[], verdicts VARCHAR[], fix_reasons JSON, tests_changed JSON, tokens BIGINT, cost_usd DOUBLE, agent VARCHAR, reviewer VARCHAR)[]',
    'usage': 'STRUCT(sessions INTEGER, log_off INTEGER, skills MAP(VARCHAR, INTEGER), agents MAP(VARCHAR, INTEGER), commands MAP(VARCHAR, INTEGER), guard_deny MAP(VARCHAR, INTEGER), guard_ask MAP(VARCHAR, INTEGER), ask_approved MAP(VARCHAR, INTEGER))'
})
WHERE kind = 'bundle';

-- One row per bundle id, its latest export: a machine that sends today's bundle every hour replaces it.
CREATE OR REPLACE VIEW bundles AS
SELECT * EXCLUDE (newest) FROM (
    SELECT *, row_number() OVER (PARTITION BY bundle_id ORDER BY exported DESC, filename DESC) AS newest
    FROM bundle_files
) WHERE newest = 1;

-- One row per loop run, however many bundles carried it, with the factory version that sent it.
CREATE OR REPLACE VIEW loop_runs AS
SELECT DISTINCT ON (r.run) node, "user", factory_commit, factory_version, r.*
FROM (
    SELECT node, "user", exported, factory."commit" AS factory_commit, factory.changelog AS factory_version,
           unnest(loop) AS r
    FROM bundles
)
ORDER BY r.run, exported DESC;

-- The bundles whose counts are summed. A bundle's usage covers its whole period with no per-day split, so
-- where two of one person's bundles cover the same day, only one is counted: the longer period, then the
-- later export. A sprint bundle wins over the daily ones inside it. Days only a dropped bundle covered are
-- left out rather than counted twice. Daily bundles from --auto never overlap.
CREATE OR REPLACE VIEW counted AS
SELECT b.* FROM bundles b
WHERE NOT EXISTS (
    SELECT 1 FROM bundles o
    WHERE o.node = b.node AND o."user" = b."user" AND o.bundle_id <> b.bundle_id
      AND o.period."first" <= b.period."last" AND b.period."first" <= o.period."last"
      AND (o.period."last" - o.period."first", o.exported, o.bundle_id)
          > (b.period."last" - b.period."first", b.exported, b.bundle_id)
);

-- Skills, agents, slash commands and the guard's refusals and asks, one row per name per counted bundle.
CREATE OR REPLACE VIEW usage_names AS
SELECT node, "user", period."first" AS first_day, period."last" AS last_day, kind, entry."key" AS name,
       entry."value" AS times
FROM (
    SELECT node, "user", period, 'skill' AS kind, unnest(map_entries(usage.skills)) AS entry FROM counted
    UNION ALL SELECT node, "user", period, 'agent', unnest(map_entries(usage.agents)) FROM counted
    UNION ALL SELECT node, "user", period, 'command', unnest(map_entries(usage.commands)) FROM counted
    UNION ALL SELECT node, "user", period, 'guard_deny', unnest(map_entries(usage.guard_deny)) FROM counted
    UNION ALL SELECT node, "user", period, 'guard_ask', unnest(map_entries(usage.guard_ask)) FROM counted
    UNION ALL SELECT node, "user", period, 'ask_approved', unnest(map_entries(usage.ask_approved)) FROM counted
);

CREATE OR REPLACE VIEW heartbeats AS
SELECT node, ts, factory, loops FROM read_json('${USAGE_ROOT}/accepted/*/heartbeat/*.json', ignore_errors = true, columns = {
    'v': 'INTEGER', 'kind': 'VARCHAR', 'node': 'VARCHAR', 'ts': 'TIMESTAMPTZ',
    'factory': 'STRUCT("commit" VARCHAR, changelog VARCHAR)',
    'loops': 'STRUCT(label VARCHAR, alive BOOLEAN, on_purpose BOOLEAN, waiting INTEGER, issue BIGINT, tokens BIGINT, budget BIGINT)[]'
})
WHERE kind = 'heartbeat';

-- Each node's latest heartbeat, one row per loop on it.
CREATE OR REPLACE VIEW loop_beats AS
SELECT node, ts, l.* FROM (
    SELECT node, ts, unnest(loops) AS l FROM (
        SELECT *, row_number() OVER (PARTITION BY node ORDER BY ts DESC) AS newest FROM heartbeats
    ) WHERE newest = 1
);
