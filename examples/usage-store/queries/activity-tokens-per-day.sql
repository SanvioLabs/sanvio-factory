-- Activity: the loop's tokens each day, a series for each node.
SELECT date_trunc('day', CAST(started AS TIMESTAMP)) AS time, node, CAST(sum(tokens) AS DOUBLE) AS tokens
FROM loop_runs
GROUP BY 1, 2
ORDER BY 1, 2;
