-- Activity: loop runs started at each hour of the day, on the node's own clock, averaged over every weekday
-- and every weekend day from the first run in the store to the last, quiet days included.
WITH r AS (SELECT CAST(started AS TIMESTAMP) AS t FROM loop_runs),
span AS (SELECT unnest(generate_series(lo, hi, INTERVAL 1 DAY)) AS day
         FROM (SELECT CAST(min(t) AS DATE) AS lo, CAST(max(t) AS DATE) AS hi FROM r) WHERE lo IS NOT NULL),
d AS (SELECT count(*) FILTER (WHERE dayofweek(day) NOT IN (0, 6)) AS weekdays,
             count(*) FILTER (WHERE dayofweek(day) IN (0, 6)) AS weekend_days FROM span)
SELECT lpad(CAST(h.hour AS VARCHAR), 2, '0') AS hour,
       round(count(r.t) FILTER (WHERE dayofweek(r.t) NOT IN (0, 6)) / nullif(any_value(d.weekdays), 0), 2) AS weekday,
       round(count(r.t) FILTER (WHERE dayofweek(r.t) IN (0, 6)) / nullif(any_value(d.weekend_days), 0), 2) AS weekend
FROM range(24) h(hour) CROSS JOIN d LEFT JOIN r ON hour(r.t) = h.hour
GROUP BY h.hour
ORDER BY h.hour;
