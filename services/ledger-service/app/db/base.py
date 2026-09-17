from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for every ledger-service ORM model.

    Only ledger-service's own tables (ledger_accounts, postings,
    ledger_entries, account_balances, holds, outbox_events) are ever
    mapped here — database-per-service means this Base never sees another
    service's tables.
    """
