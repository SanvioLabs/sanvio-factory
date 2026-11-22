-- RQ-2: What does a pull request cost, by project and by agent? Cost is the loop's estimate at API prices.
SELECT coalesce(project, 'factory') AS project, agent, count(*) AS pull_requests,
       round(sum(cost_usd), 2) AS cost_usd, round(sum(cost_usd) / count(*), 2) AS usd_per_pr,
       CAST(sum(tokens) // count(*) AS BIGINT) AS tokens_per_pr
FROM loop_runs
WHERE outcome = 'pr'
GROUP BY project, agent
ORDER BY cost_usd DESC NULLS LAST, project, agent;
