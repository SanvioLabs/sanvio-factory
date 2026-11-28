-- RQ-5: Is every node's loop running, and when did each last report?
SELECT node, max(ts) AS last_heartbeat, date_diff('minute', max(ts), now()) AS minutes_since,
       count(*) FILTER (WHERE alive) AS loops_alive,
       count(*) FILTER (WHERE NOT alive AND coalesce(on_purpose, false)) AS loops_stopped_on_purpose, count(*) AS loops, CAST(sum(waiting) AS BIGINT) AS waiting
FROM loop_beats
GROUP BY node
ORDER BY minutes_since DESC, node;
