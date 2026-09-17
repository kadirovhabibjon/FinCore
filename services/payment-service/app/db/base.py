from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for every payment-service ORM model.

    Only payment-service's own tables (transfers, payments, refunds,
    merchants, idempotency_keys, outbox_events, processed_events) are
    ever mapped here — database-per-service means this Base never sees
    another service's tables.
    """
