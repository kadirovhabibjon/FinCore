from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for every fraud-service ORM model.

    Only fraud-service's own tables (fraud_checks) are ever mapped here
    — database-per-service means this Base never sees another service's
    tables.
    """
