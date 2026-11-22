-- RQ-6: Which shell commands do agents run most, and which get refused or asked about? Detailed mode only:
-- this reads the commands view, which only the owner's data source has.
SELECT split_part(trim("text"), ' ', 1) AS program, count(*) AS runs,
       count(*) FILTER (WHERE verdict = 'refused') AS refused, count(*) FILTER (WHERE verdict = 'asked') AS asked,
       count(DISTINCT "user") AS people
FROM commands
GROUP BY program
ORDER BY runs DESC, program;
