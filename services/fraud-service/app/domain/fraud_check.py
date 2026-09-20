import enum
import uuid
from datetime import datetime

from sqlalchemy import ARRAY, BigInteger, DateTime, Enum, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FraudDecision(enum.StrEnum):
    ALLOW = "ALLOW"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


class FraudCheck(Base):
    """One risk assessment (spec Section 12: "every check is stored...
    with the rules triggered and the score, for audit and tuning").
    Append-only in practice — nothing in this service ever updates a
    row after insert.

    `(operation_id, operation_type)` is the idempotency key: a retried
    risk check for the same operation returns the stored result instead
    of re-scoring (and, more importantly, instead of double-counting
    itself in the frequency-based rules' own history lookups).
    `operation_id` alone (a UUID minted by the caller, e.g. a Transfer's
    own id) is already effectively unique on its own; `operation_type`
    is paired with it only for the same reason ledger-service pairs
    `source_id` with `type` — a future second operation type sharing an
    id space with the first would otherwise collide. No `source_service`
    field: fraud-service has exactly one caller today (payment-service,
    spec Section 12), so it isn't part of the request payload.
    """

    __tablename__ = "fraud_checks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    operation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    operation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[FraudDecision] = mapped_column(
        Enum(FraudDecision, name="fraud_decision", native_enum=True), nullable=False
    )
    rules_triggered: Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "operation_id",
            "operation_type",
            name="uq_fraud_checks_operation_idempotency",
        ),
    )
