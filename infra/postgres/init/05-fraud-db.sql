-- Same reasoning as 01-identity-db.sql: a dedicated, least-privilege
-- role scoped to fraud_db only, never the postgres superuser.
CREATE USER fraud WITH PASSWORD 'fraud';
CREATE DATABASE fraud_db OWNER fraud;
