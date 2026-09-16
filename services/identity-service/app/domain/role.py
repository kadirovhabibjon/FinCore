import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RoleName(str, enum.Enum):
    """The fixed set of role names FinCore ships with (spec Section 5).

    Roles themselves are still a real table (not just this enum): Section
    21 lists `roles` as data identity-service owns, which leaves room for
    a role to carry more than a name later (e.g. a description, or
    permissions) without a schema rewrite. This enum exists only so
    application code never spells a role name as a bare string.
    """

    USER = "USER"
    SUPPORT = "SUPPORT"
    ADMIN = "ADMIN"


class Role(Base):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)


class UserRole(Base):
    """Many-to-many link between users and roles.

    A row's existence *is* the grant; `assigned_at` exists so "when was
    this role granted" is answerable without a separate audit log entry
    for what is, in practice, a rare event.
    """

    __tablename__ = "user_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role_name: Mapped[str] = mapped_column(
        String(32), ForeignKey("roles.name"), primary_key=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
