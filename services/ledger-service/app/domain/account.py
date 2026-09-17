import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AccountKind(enum.StrEnum):
    """Account kinds and their normal balance side (ADR-0002):

    USER_WALLET / MERCHANT_SETTLEMENT / FEES  -> CREDIT-normal (liability/revenue)
    EXTERNAL_FUNDING                          -> DEBIT-normal  (clearing)
    EXTERNAL_PAYOUT                           -> CREDIT-normal (clearing)
    SUSPENSE                                  -> no normal side; must net to zero
    """

    USER_WALLET = "USER_WALLET"
    EXTERNAL_FUNDING = "EXTERNAL_FUNDING"
    EXTERNAL_PAYOUT = "EXTERNAL_PAYOUT"
    MERCHANT_SETTLEMENT = "MERCHANT_SETTLEMENT"
    FEES = "FEES"
    SUSPENSE = "SUSPENSE"


class AccountStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    FROZEN = "FROZEN"
    CLOSED = "CLOSED"


class LedgerAccount(Base):
    """A ledger account: a customer wallet (`USER_WALLET`, carries
    `owner_user_id`) or one of the fixed system accounts every currency
    needs as a counterparty for money entering/leaving FinCore, or moving
    to a merchant/fee account (ADR-0002, spec Section 8.1).

    ledger-service treats every account the same way regardless of kind —
    it only enforces the sign convention and balance invariants. It does
    not know *why* a posting touches a given account; that intention
    belongs entirely to payment-service (context-map.md Section 3).
    """

    __tablename__ = "ledger_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    kind: Mapped[AccountKind] = mapped_column(
        Enum(AccountKind, name="account_kind", native_enum=True), nullable=False
    )
    # Set only for USER_WALLET; NULL for every system account kind —
    # enforced below by ck_ledger_accounts_wallet_has_owner.
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[AccountStatus] = mapped_column(
        Enum(AccountStatus, name="account_status", native_enum=True),
        nullable=False,
        default=AccountStatus.ACTIVE,
        server_default=AccountStatus.ACTIVE.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "(kind = 'USER_WALLET' AND owner_user_id IS NOT NULL) OR "
            "(kind != 'USER_WALLET' AND owner_user_id IS NULL)",
            name="ck_ledger_accounts_wallet_has_owner",
        ),
        # v1: one wallet per (owner_user_id, currency) — spec Section 6.
        # A plain UNIQUE(owner_user_id, currency) would not work: SQL
        # treats every NULL as distinct, so it wouldn't stop duplicate
        # *system* accounts (owner_user_id always NULL) from being
        # created — hence two separate partial indexes instead of one
        # constraint covering both cases.
        Index(
            "uq_ledger_accounts_wallet_per_owner_currency",
            "owner_user_id",
            "currency",
            unique=True,
            postgresql_where=text("owner_user_id IS NOT NULL"),
        ),
        # Exactly one of each system account kind per currency.
        Index(
            "uq_ledger_accounts_system_per_kind_currency",
            "kind",
            "currency",
            unique=True,
            postgresql_where=text("owner_user_id IS NULL"),
        ),
    )
