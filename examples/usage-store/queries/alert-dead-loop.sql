-- REQ-015: a loop whose machine still sends heartbeats but whose loop has stopped. 1 per stopped loop, from
-- each node's latest heartbeat; the rule fires on any.
SELECT node || '/' || label AS loop, CASE WHEN alive THEN 0 ELSE 1 END AS stopped
FROM loop_beats;
