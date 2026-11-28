-- REQ-015: a loop whose machine still sends heartbeats but whose loop died: killed, or ended on an error. 1 per
-- such loop, from each node's latest heartbeat; the rule fires on any. A loop stopped on purpose, or that never
-- ran, isn't counted (on_purpose), and a heartbeat from before that key counts as before.
SELECT node || '/' || label AS loop, CASE WHEN alive OR coalesce(on_purpose, false) THEN 0 ELSE 1 END AS stopped
FROM loop_beats;
