-- Activity: loop runs started each hour over the last week, a series for each node. Eight days, so a node
-- whose clock is ahead of the viewer's still shows its whole week.
SELECT date_trunc('hour', CAST(started AS TIMESTAMP)) AS time, node, count(*) AS runs
FROM loop_runs
WHERE CAST(started AS TIMESTAMP) > now() - INTERVAL 8 DAY
GROUP BY 1, 2
ORDER BY 1, 2;
