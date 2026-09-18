from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for every notification-service ORM model.

    Only notification-service's own tables (notifications) are ever
    mapped here — database-per-service means this Base never sees
    another service's tables.
    """
