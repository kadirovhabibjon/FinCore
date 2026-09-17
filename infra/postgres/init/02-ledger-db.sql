-- Same reasoning as 01-identity-db.sql: a dedicated, least-privilege
-- role scoped to ledger_db only, never the postgres superuser.
CREATE USER ledger WITH PASSWORD 'ledger';
CREATE DATABASE ledger_db OWNER ledger;
