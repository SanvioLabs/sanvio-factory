-- RQ-1: Which skills, agents and slash commands did the team use, and which went unused?
-- A name whose last_used is weeks old is one the team stopped using.
SELECT kind, name, CAST(sum(times) AS BIGINT) AS times, count(DISTINCT "user") AS people, max(last_day) AS last_used
FROM usage_names
WHERE kind IN ('skill', 'agent', 'command')
GROUP BY kind, name
ORDER BY kind, times DESC, name;
