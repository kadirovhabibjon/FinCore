from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for every identity-service ORM model.

    Only identity-service's own tables (users, roles, sessions, refresh
    tokens, outbox_events) are ever mapped here — database-per-service
    means this Base never sees another service's tables.
    """
