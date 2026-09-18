-- Same reasoning as 01-identity-db.sql: a dedicated, least-privilege
-- role scoped to payment_db only, never the postgres superuser.
CREATE USER payment WITH PASSWORD 'payment';
CREATE DATABASE payment_db OWNER payment;
