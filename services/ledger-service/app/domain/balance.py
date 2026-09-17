import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.account import AccountKind


class AccountBalance(Base):
    """The current projected balance of a ledger account — a cache of the
    entry log's sum, not a second source of truth (ADR-0002). Row-locked
    with `SELECT ... FOR UPDATE` before every mutation; see
    app/repositories/account_repository.py.
    """

    __tablename__ = "account_balances"

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ledger_accounts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # Denormalized from ledger_accounts.kind, set once at creation and
    # never changed. A plain CHECK constraint cannot reference another
    # table's column, and the invariant below is a real one (spec
    # Section 8.3), not just an application-level convention a future
    # bug could silently skip — so the value the CHECK needs lives on
    # this row too.
    # postgresql.ENUM specifically, not generic sqlalchemy.Enum:
    # create_type=False is only honored by the dialect-specific class —
    # confirmed empirically (see the matching comment in this table's
    # migration) after generic Enum(create_type=False) still emitted a
    # duplicate CREATE TYPE.
    kind: Mapped[AccountKind] = mapped_column(
        ENUM(AccountKind, name="account_kind", create_type=False),
        nullable=False,
    )
    balance_minor: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    held_minor: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "kind != 'USER_WALLET' OR balance_minor - held_minor >= 0",
            name="ck_account_balances_wallet_available_non_negative",
        ),
    )
