-- RQ-4: Where does the guard refuse or ask most, and which asks do people always say yes to?
-- An ask whose approved equals asked is one people always say yes to: a candidate to loosen.
SELECT name, CAST(sum(times) FILTER (WHERE kind = 'guard_deny') AS BIGINT) AS refused,
       CAST(sum(times) FILTER (WHERE kind = 'guard_ask') AS BIGINT) AS asked,
       CAST(sum(times) FILTER (WHERE kind = 'ask_approved') AS BIGINT) AS approved
FROM usage_names
WHERE kind IN ('guard_deny', 'guard_ask', 'ask_approved')
GROUP BY name
ORDER BY coalesce(refused, 0) + coalesce(asked, 0) DESC, name;
