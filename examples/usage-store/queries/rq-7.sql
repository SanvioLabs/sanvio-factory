-- RQ-7: What does an issue that reached a pull request cost all in, counting every loop run on it, and how much
-- loop spend sits on issues that have no pull request yet, by project? A pull request here is one the loop
-- opened, not one that merged. Cost is the loop's estimate at API prices. A run with no cost, such as one the
-- budget stopped, is in no sum: unpriced_runs counts them, and where it isn't 0, all_in_cost_usd,
-- no_pr_cost_usd and no_pr_percent are lower than the real spend. usd_per_issue averages only the issues whose
-- every run recorded a cost, so an unpriced run never pulls it down. An issue whose runs recorded no cost
-- still counts in issues_with_pr, and a sum with no cost in it shows null, not 0. A run with no outcome counts
-- as no pull request, and a run with no issue stands alone. As in RQ-2, a project named factory shares the
-- factory's own row.
SELECT coalesce(project, 'factory') AS project, count(*) FILTER (WHERE reached) AS issues_with_pr,
       round(sum(cost) FILTER (WHERE reached), 2) AS all_in_cost_usd,
       round(sum(cost) FILTER (WHERE reached AND priced)
             / nullif(count(*) FILTER (WHERE reached AND priced), 0), 2) AS usd_per_issue,
       round(sum(cost) FILTER (WHERE NOT reached), 2) AS no_pr_cost_usd,
       round(100 * sum(cost) FILTER (WHERE NOT reached) / nullif(sum(cost), 0), 1) AS no_pr_percent,
       CAST(sum(unpriced) AS BIGINT) AS unpriced_runs
FROM (
    SELECT project, coalesce(bool_or(outcome = 'pr'), false) AS reached, sum(cost_usd) AS cost,
           bool_and(cost_usd IS NOT NULL) AS priced, count(*) FILTER (WHERE cost_usd IS NULL) AS unpriced
    FROM loop_runs
    GROUP BY project, issue, CASE WHEN issue IS NULL THEN run END
)
GROUP BY coalesce(project, 'factory')
ORDER BY all_in_cost_usd DESC NULLS LAST, project;
