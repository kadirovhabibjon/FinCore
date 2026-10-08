import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WalletLimit(Base):
    """The most a customer lets one of their wallets send in any 24
    hours - their own guard against a stolen session or a slip of the
    finger, not a rule FinCore imposes. No row means no limit.

    Here rather than in ledger-service because it is a rule about
    operations (which count, over what window), and the ledger knows
    postings, not why they were made.
    """

    __tablename__ = "wallet_limits"

    wallet_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    daily_limit_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("daily_limit_minor > 0", name="ck_wallet_limits_positive"),
    )
