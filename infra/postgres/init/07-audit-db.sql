-- Same reasoning as 01-identity-db.sql: a dedicated, least-privilege
-- role scoped to audit_db only, never the postgres superuser.
--
-- Unlike every other service's role, this one also has UPDATE, DELETE
-- and TRUNCATE revoked from it on `audit_logs` specifically — done in
-- the service's own first migration (right after `CREATE TABLE`, since
-- the role needs to own the table to create it at all), not here,
-- since Alembic hasn't created the table yet at the point this script
-- runs (spec Section 18: "no UPDATE/DELETE permissions for the
-- service's DB user").
CREATE USER audit WITH PASSWORD 'audit';
CREATE DATABASE audit_db OWNER audit;
