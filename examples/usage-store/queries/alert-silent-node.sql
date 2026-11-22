-- REQ-015: minutes since each node's last heartbeat. The alert rule fires past the node's window.
SELECT node, date_diff('minute', max(ts), now()) AS minutes_silent
FROM heartbeats
GROUP BY node;
