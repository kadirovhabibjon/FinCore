import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    SUSPENDED = "SUSPENDED"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Stored already normalized (lowercased, trimmed) — normalization
    # happens once, in the registration use case, not here, so the model
    # stays a plain mapping and the uniqueness constraint below is
    # trustworthy without needing a Postgres extension like citext.
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    phone: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, index=True
    )

    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)

    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status", native_enum=True),
        nullable=False,
        default=UserStatus.ACTIVE,
        server_default=UserStatus.ACTIVE.value,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
