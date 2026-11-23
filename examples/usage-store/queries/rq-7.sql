-- RQ-7: What does an issue that reached a pull request cost all in, counting every loop run on it, and how much
-- loop spend sits on issues that have no pull request yet, by project? A pull request here is one the loop
-- opened, not one that merged. Cost is the loop's estimate at API prices; a cost the runs never recorded stays
-- null rather than reading as 0.
SELECT coalesce(project, 'factory') AS project, count(*) FILTER (WHERE reached) AS issues_with_pr,
       round(sum(cost) FILTER (WHERE reached), 2) AS all_in_cost_usd,
       round(sum(cost) FILTER (WHERE reached) / nullif(count(*) FILTER (WHERE reached), 0), 2) AS usd_per_issue,
       round(sum(cost) FILTER (WHERE NOT reached), 2) AS no_pr_cost_usd,
       round(100 * sum(cost) FILTER (WHERE NOT reached) / nullif(sum(cost), 0), 1) AS no_pr_percent
FROM (
    SELECT project, issue, coalesce(bool_or(outcome = 'pr'), false) AS reached, sum(cost_usd) AS cost
    FROM loop_runs
    GROUP BY project, issue
)
GROUP BY coalesce(project, 'factory')
ORDER BY all_in_cost_usd DESC NULLS LAST, project;
