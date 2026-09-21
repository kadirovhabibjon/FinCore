from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for every webhook-service ORM model.

    Only webhook-service's own tables (webhook_endpoints,
    webhook_deliveries, webhook_attempts) are ever mapped here —
    database-per-service means this Base never sees another service's
    tables.
    """
