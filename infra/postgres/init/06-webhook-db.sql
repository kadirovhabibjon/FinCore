-- Same reasoning as 01-identity-db.sql: a dedicated, least-privilege
-- role scoped to webhook_db only, never the postgres superuser.
CREATE USER webhook WITH PASSWORD 'webhook';
CREATE DATABASE webhook_db OWNER webhook;
