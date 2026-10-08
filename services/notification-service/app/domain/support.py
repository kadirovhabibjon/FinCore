import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SupportSender(enum.StrEnum):
    CUSTOMER = "CUSTOMER"
    STAFF = "STAFF"


class SupportStatus(enum.StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class SupportThread(Base):
    """A customer's conversation with FinCore's staff: one per customer,
    for as long as they have the account, like a chat with a bank's
    operator - not a ticket per question. Staff mark it resolved when
    there is nothing left to answer; the customer writing again reopens
    it.

    The row carries what the staff's inbox needs without reading the
    messages: when and by whom the last one was written, how it began,
    and how many each side has not read yet. It changes only together
    with the message that changed it, under this row's lock.
    """

    __tablename__ = "support_threads"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    status: Mapped[SupportStatus] = mapped_column(
        Enum(SupportStatus, name="support_status", native_enum=True),
        nullable=False,
        default=SupportStatus.OPEN,
        server_default=SupportStatus.OPEN.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_sender: Mapped[SupportSender] = mapped_column(
        Enum(SupportSender, name="support_sender", native_enum=True), nullable=False
    )
    # The start of the last message, for the inbox.
    last_body: Mapped[str] = mapped_column(String(200), nullable=False)
    # Messages from the customer no staff member has opened yet, and
    # replies the customer has not opened yet.
    staff_unread: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    customer_unread: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    __table_args__ = (Index("ix_support_threads_inbox", "status", "last_message_at"),)


class SupportMessage(Base):
    __tablename__ = "support_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Whose conversation it belongs to (SupportThread.user_id).
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sender: Mapped[SupportSender] = mapped_column(
        Enum(SupportSender, name="support_sender", native_enum=True), nullable=False
    )
    # Which staff member wrote a STAFF message; never shown to the customer.
    staff_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    body: Mapped[str] = mapped_column(String(2000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_support_messages_thread", "user_id", "created_at"),)
