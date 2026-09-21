from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for every audit-service ORM model.

    Only audit-service's own tables (audit_logs, dead_letters) are ever
    mapped here — database-per-service means this Base never sees
    another service's tables.
    """
