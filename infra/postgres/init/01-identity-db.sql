-- Runs once, automatically, when the postgres container's data directory
-- is empty (docker-entrypoint-initdb.d convention).
--
-- Section 19 ("least-privilege DB users per service"): identity-service
-- never connects as the postgres superuser. It gets its own login role,
-- scoped to a database it owns and nothing else — exactly the database
-- isolation database-per-service is meant to enforce, applied at the
-- Postgres role level too, not just the application layer.
--
-- Dev-only credentials, checked in on purpose: this creates a role
-- inside a Docker network the developer's own machine controls, not a
-- deployed secret. A real environment supplies its own password via
-- secrets management, not this file.
CREATE USER identity WITH PASSWORD 'identity';
CREATE DATABASE identity_db OWNER identity;
