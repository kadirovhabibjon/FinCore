import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PostingType(enum.StrEnum):
    """Mirrors the business operation types (spec Section 7.1). A posting
    always exists *because* payment-service asked for one of these; the
    type is recorded so `(source_service, source_id, type)` can be a
    precise idempotency key — the same transfer could in principle
    produce more than one posting type over its life (e.g. a payment's
    capture vs. its later refund).
    """

    TRANSFER = "TRANSFER"
    PAYMENT = "PAYMENT"
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    REFUND = "REFUND"


class EntryDirection(enum.StrEnum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class Posting(Base):
    """A balanced, atomic accounting fact (ADR-0002). Append-only: never
    UPDATEd or DELETEd after creation — see app/services/postings.py for
    where that's enforced.
    """

    __tablename__ = "postings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_service: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[PostingType] = mapped_column(
        Enum(PostingType, name="posting_type", native_enum=True), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # Posting idempotency (ADR-0002 / spec Section 8.3): retrying a
        # posting call for the same business operation returns the
        # existing posting instead of creating a duplicate.
        UniqueConstraint(
            "source_service", "source_id", "type", name="uq_postings_source_idempotency"
        ),
    )


class LedgerEntry(Base):
    """One line of a posting: a single (account, direction, amount)."""

    __tablename__ = "ledger_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    posting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("postings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ledger_accounts.id"), nullable=False, index=True
    )
    direction: Mapped[EntryDirection] = mapped_column(
        Enum(EntryDirection, name="entry_direction", native_enum=True), nullable=False
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="ck_ledger_entries_amount_positive"),
    )
