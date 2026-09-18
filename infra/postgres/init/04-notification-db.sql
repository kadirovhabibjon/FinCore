-- Same reasoning as 01-identity-db.sql: a dedicated, least-privilege
-- role scoped to notification_db only, never the postgres superuser.
CREATE USER notification WITH PASSWORD 'notification';
CREATE DATABASE notification_db OWNER notification;
