from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fincore_common import normalize_card_number
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import AuthenticatedUser, get_authenticated_user
from app.core.amounts import parse_positive_amount
from app.core.exceptions import (
    AmountOutOfRangeError,
    InvalidTemplateError,
    ServiceNotFoundError,
    TemplateNotFoundError,
    TooManyTemplatesError,
)
from app.db.session import get_db
from app.domain.template import Template, TemplateKind
from app.services import billers
from app.services.recipients import find_recipient

router = APIRouter(prefix="/api/v1/templates", tags=["templates"])

# Enough for everything a person pays regularly; a list longer than this
# is no longer a shortcut.
MAX_TEMPLATES = 30


class CreateTemplateRequest(BaseModel):
    # What the customer calls it, e.g. "Home internet".
    name: str = Field(min_length=1, max_length=60)
    kind: TemplateKind
    # SERVICE: the provider's code and the account there, as typed.
    service_code: str | None = Field(default=None, max_length=32)
    account: str | None = Field(default=None, max_length=64)
    # TRANSFER: the recipient's FinCore card number.
    card_number: str | None = Field(default=None, max_length=32)
    # Decimal string; omit to type the amount each time.
    amount: str | None = Field(default=None, max_length=32)

    @field_validator("name")
    @classmethod
    def _one_line(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned


class TemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: TemplateKind
    name: str
    service_code: str | None
    service_account: str | None
    card_number: str | None
    # The recipient's name when the template was saved ("Aziza K.").
    recipient_name: str | None
    currency: str
    # Null: the amount is typed each time.
    amount_minor: int | None
    created_at: datetime


@router.get("", response_model=list[TemplateResponse])
async def list_my_templates(
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> list[TemplateResponse]:
    """The caller's saved payments, newest first."""
    result = await session.execute(
        select(Template)
        .where(Template.owner_user_id == user.user_id)
        .order_by(Template.created_at.desc(), Template.id)
    )
    return [TemplateResponse.model_validate(item) for item in result.scalars().all()]


@router.post("", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def save_template(
    payload: CreateTemplateRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> TemplateResponse:
    """Saves a payment to make again: a service provider and an account
    there, or a recipient's card - checked now the way the payment
    itself would check them. Saving moves nothing; using a template
    only fills the form in."""
    template = Template(owner_user_id=user.user_id, kind=payload.kind, name=payload.name)

    if payload.kind is TemplateKind.SERVICE:
        if not payload.service_code or not payload.account or payload.card_number:
            raise InvalidTemplateError("a service template has service_code and account")
        biller = billers.find(payload.service_code)
        if biller is None:
            raise ServiceNotFoundError(payload.service_code)
        template.service_code = biller.code
        template.service_account = billers.clean_account(biller, payload.account)
        template.currency = biller.currency
        if payload.amount is not None:
            template.amount_minor = parse_positive_amount(payload.amount, biller.currency)
            if not biller.min_amount_minor <= template.amount_minor <= biller.max_amount_minor:
                raise AmountOutOfRangeError(f"{biller.name} does not take this amount")
    else:
        if not payload.card_number or payload.service_code or payload.account:
            raise InvalidTemplateError("a transfer template has card_number")
        # The same lookup the Send page makes: a card that can't receive
        # money is not worth saving, and this is where the name and the
        # currency come from.
        recipient = await find_recipient(payload.card_number, caller_user_id=user.user_id)
        template.card_number = normalize_card_number(payload.card_number)
        template.recipient_name = recipient.display_name
        template.currency = recipient.currency
        if payload.amount is not None:
            template.amount_minor = parse_positive_amount(payload.amount, recipient.currency)

    # Not locked: two saves at the same instant could end one over the
    # limit. It is a limit on clutter, not on money.
    count = await session.execute(
        select(func.count()).select_from(Template).where(Template.owner_user_id == user.user_id)
    )
    if count.scalar_one() >= MAX_TEMPLATES:
        raise TooManyTemplatesError(f"at most {MAX_TEMPLATES} templates; delete one first")

    session.add(template)
    await session.commit()
    await session.refresh(template)
    return TemplateResponse.model_validate(template)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: UUID,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    template = await session.get(Template, template_id)
    if template is None or template.owner_user_id != user.user_id:
        raise TemplateNotFoundError(str(template_id))
    await session.delete(template)
    await session.commit()
