import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TemplateKind(enum.StrEnum):
    # A payment to a service provider, for an account there.
    SERVICE = "SERVICE"
    # A transfer to a FinCore card.
    TRANSFER = "TRANSFER"


class Template(Base):
    """Something a customer pays again and again, saved so the form
    comes filled in: who or what, and optionally how much. It is a
    bookmark, not an instruction - nothing is ever paid from a template
    without the customer pressing Pay on the form it fills, where the
    recipient is looked up again and every rule of a payment applies.
    """

    __tablename__ = "templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    kind: Mapped[TemplateKind] = mapped_column(
        Enum(TemplateKind, name="template_kind", native_enum=True), nullable=False
    )
    # The customer's own name for it.
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    # SERVICE: which provider (app/services/billers.py) and the account
    # there, in its stored form.
    service_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    service_account: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # TRANSFER: the recipient's card, and their name as it was when the
    # template was saved (shown on the tile; looked up afresh on use).
    card_number: Mapped[str | None] = mapped_column(String(16), nullable=True)
    recipient_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    # Null: the amount is typed each time.
    amount_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "(kind = 'SERVICE' AND service_code IS NOT NULL AND service_account IS NOT NULL"
            " AND card_number IS NULL) OR "
            "(kind = 'TRANSFER' AND card_number IS NOT NULL AND service_code IS NULL"
            " AND service_account IS NULL)",
            name="ck_templates_fields_match_kind",
        ),
        CheckConstraint(
            "amount_minor IS NULL OR amount_minor > 0", name="ck_templates_amount_positive"
        ),
    )
