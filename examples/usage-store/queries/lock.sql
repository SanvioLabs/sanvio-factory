-- Last in every data source's init SQL (SPEC-004 SEC review, F08): once the views exist, DuckDB may read the
-- store and nothing else, write nowhere, and nobody can change that from a query. A viewer who posts their
-- own SQL to Grafana gets the store's numbers and no file on the machine.
SET allowed_directories = ['${USAGE_ROOT}/'];
SET enable_external_access = false;
SET lock_configuration = true;
