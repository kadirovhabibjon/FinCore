import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CodePurpose(enum.StrEnum):
    # Finishing a sign-in on an account with two-step sign-in.
    LOGIN = "LOGIN"
    # Proving the email address works before two-step sign-in is turned on.
    ENABLE = "ENABLE"


class LoginCode(Base):
    """One emailed code for two-step sign-in. Like a password reset
    code, only its hash is stored and it works once, for a few minutes
    and a limited number of guesses. Its id is the "challenge" the
    client presents with the code: random, handed only to whoever has
    just given the right password, so the six digits alone are useless
    to anyone else."""

    __tablename__ = "login_codes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purpose: Mapped[CodePurpose] = mapped_column(
        Enum(CodePurpose, name="login_code_purpose", native_enum=True), nullable=False
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Wrong codes tried against this one.
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Set when it was used, or replaced by a newer code.
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
