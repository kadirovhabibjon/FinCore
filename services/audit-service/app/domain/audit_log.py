import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditLog(Base):
    """One audited fact (spec Section 18): who, what, which resource,
    when, from where, and the result. `action`/`result` are plain
    strings, not native enums — an audit trail records whatever a
    producer actually emitted, including a value this service has never
    seen before, rather than rejecting it for not matching a fixed list.

    `actor_role`, `ip_address` and `user_agent` are nullable and, today,
    always null: the events this service currently consumes
    (`transfer.completed` etc.) don't carry that information — see the
    README for why extending the producers to capture it is out of
    scope for now rather than silently fabricated here.

    **Append-only**: this table's migration revokes UPDATE/DELETE/
    TRUNCATE from the `audit` role after creating it (spec Section 18:
    "no UPDATE/DELETE permissions for the service's DB user") — enforced
    by PostgreSQL itself, not just by this service never issuing those
    statements.
    """

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # The upstream EventEnvelope.event_id — UNIQUE, and this service's
    # only idempotency guard against Kafka's at-least-once redelivery
    # (spec Section 14.1). No separate `processed_events` table, same
    # realized pattern as notification-service's `notifications.event_id`.
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    actor_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Additional context that doesn't warrant its own column (amount,
    # currency, reference, failure reason, ...) — never passwords,
    # tokens, full card data or secret keys (spec Section 18), which
    # none of this service's current source events carry anyway.
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # When the audited action itself happened (the source EventEnvelope's
    # own occurred_at), distinct from `created_at` — when this row was
    # written, which lags behind by however long the event took to
    # arrive and be processed.
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
