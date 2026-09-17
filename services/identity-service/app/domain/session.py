import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Session(Base):
    """A login session — the "family" a refresh token belongs to.

    Rotation creates new RefreshToken rows under the same session; revoking
    a session (logout, or reuse detection below) invalidates every token
    that will ever be issued for it, without having to touch each token
    row individually.
    """

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class RefreshToken(Base):
    """One issued refresh token, identified in the database only by the
    SHA-256 hash of its plaintext value — the plaintext is returned to the
    caller exactly once and never stored.

    A fast hash (not Argon2) is deliberate here: this token is a 256-bit
    random value, not a user-chosen password, so there is no low-entropy
    guessing risk for a slow hash to defend against — only a fast lookup
    is needed on every refresh call.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Non-null means "already redeemed for a new token". A second attempt
    # to redeem the same token — genuine replay or a concurrent duplicate
    # request — is exactly what this column, claimed atomically, detects.
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
