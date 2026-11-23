-- RQ-7: What does an issue that reached a pull request cost all in, counting every loop run on it, and how much
-- loop spend sits on issues that have no pull request yet, by project? A pull request here is one the loop
-- opened, not one that merged. Cost is the loop's estimate at API prices. An issue is priced only when every
-- run on it recorded a cost: a run the budget stopped before a result came has none, so an issue with such a
-- run drops out of every cost column whole, known runs included, rather than showing too low a figure. The
-- unpriced_issues column counts those, and a project whose issues are all unpriced shows null, not 0. A run
-- with no outcome counts as no pull request. As in RQ-2, a project named factory shares the factory's own row.
SELECT coalesce(project, 'factory') AS project, count(*) FILTER (WHERE reached) AS issues_with_pr,
       round(sum(cost) FILTER (WHERE reached), 2) AS all_in_cost_usd,
       round(sum(cost) FILTER (WHERE reached) / nullif(count(cost) FILTER (WHERE reached), 0), 2) AS usd_per_issue,
       round(sum(cost) FILTER (WHERE NOT reached), 2) AS no_pr_cost_usd,
       round(100 * sum(cost) FILTER (WHERE NOT reached) / nullif(sum(cost), 0), 1) AS no_pr_percent,
       count(*) - count(cost) AS unpriced_issues
FROM (
    SELECT project, issue, coalesce(bool_or(outcome = 'pr'), false) AS reached,
           CASE WHEN count(cost_usd) = count(*) THEN sum(cost_usd) END AS cost
    FROM loop_runs
    GROUP BY project, issue
)
GROUP BY coalesce(project, 'factory')
ORDER BY all_in_cost_usd DESC NULLS LAST, project;
