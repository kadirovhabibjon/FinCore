import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IdempotencyKeyStatus(enum.StrEnum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class IdempotencyKey(Base):
    """Public-API idempotency (spec Section 9.1) — reusable across any
    idempotent endpoint, not just transfers.

    The UNIQUE(user_id, key) constraint is what actually wins races
    between two concurrent duplicate requests carrying the same key: the
    first INSERT succeeds, the second hits the constraint and the caller
    treats that exactly like finding the row via a pre-check ("let the
    database decide" — the same pattern used throughout this project,
    e.g. registration, refresh token rotation).
    """

    __tablename__ = "idempotency_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    # SHA-256 hex digest of method + path + canonical request body — lets
    # a reused key with a *different* body be detected and rejected
    # (422), distinct from a genuine retry (same body).
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[IdempotencyKeyStatus] = mapped_column(
        Enum(IdempotencyKeyStatus, name="idempotency_key_status", native_enum=True),
        nullable=False,
        default=IdempotencyKeyStatus.IN_PROGRESS,
        server_default=IdempotencyKeyStatus.IN_PROGRESS.value,
    )
    response_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_idempotency_keys_user_key"),)
