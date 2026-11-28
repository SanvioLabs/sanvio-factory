-- Activity: loop runs started each hour, every node together. A run's start is its node's own clock, as the
-- loop writes it, with no time zone.
SELECT date_trunc('hour', CAST(started AS TIMESTAMP)) AS time, count(*) AS runs
FROM loop_runs
GROUP BY 1
ORDER BY 1;
