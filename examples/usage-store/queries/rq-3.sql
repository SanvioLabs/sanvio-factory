-- RQ-3: How many fix rounds does an issue take, by agent, reviewer and factory version?
SELECT agent, reviewer, coalesce(factory_version, 'unknown') AS factory_version, count(*) AS runs,
       round(avg(rounds), 2) AS mean_rounds, max(rounds) AS most_rounds
FROM loop_runs
GROUP BY agent, reviewer, factory_version
ORDER BY factory_version DESC, agent, reviewer;
