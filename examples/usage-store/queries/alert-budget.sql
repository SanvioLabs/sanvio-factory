-- REQ-015: how much of its token budget each running issue has spent, from each node's latest heartbeat.
SELECT node || '/' || label || '#' || CAST(issue AS VARCHAR) AS run, 100.0 * tokens / budget AS percent_of_budget
FROM loop_beats
WHERE issue IS NOT NULL AND tokens IS NOT NULL AND budget > 0;
