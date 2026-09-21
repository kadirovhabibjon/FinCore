import logging
from dataclasses import dataclass
from uuid import UUID

from fincore_common import EventType
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.payment import PaymentStatus
from app.domain.refund import Refund, RefundStatus
from app.repositories.payment_repository import PaymentRepository
from app.repositories.refund_repository import RefundRepository
from app.services import ledger
from app.services.ledger import PostingOutcome
from app.services.payments import payment_outbox_event

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CreateRefundInput:
    payment_id: UUID
    idempotency_key_id: UUID
    amount_minor: int
    reason: str | None = None


async def create_refund(session: AsyncSession, data: CreateRefundInput) -> Refund:
    """Creates a Refund and attempts its posting (spec Section 11:
    "refunds as new postings, never by editing old ones"). Eligibility
    (payment status, amount within the remaining refundable balance) is
    the caller's responsibility to check *before* this — same ordering
    as `POST /api/v1/transfers`' "authorize -> validate -> idempotency
    check -> create."
    """
    refund = Refund(
        payment_id=data.payment_id,
        amount_minor=data.amount_minor,
        reason=data.reason,
        idempotency_key_id=data.idempotency_key_id,
    )
    session.add(refund)
    await session.commit()
    await session.refresh(refund)

    return await attempt_refund_posting(session, refund)


async def attempt_refund_posting(session: AsyncSession, refund: Refund) -> Refund:
    """Looks up the MERCHANT_SETTLEMENT account for the payment's
    currency, then posts the refund: DEBIT the merchant's settlement,
    CREDIT the payer's original wallet. Shared by `create_refund` (the
    first attempt) and the recovery worker (retrying a refund left
    PENDING by an earlier unknown outcome) — safe to call more than
    once, since `create_posting` is idempotent on
    `(source_service, source_id, type)` and `source_id` here is the
    refund's own id, fixed at creation.
    """
    payment_repository = PaymentRepository(session)
    refund_repository = RefundRepository(session)
    payment = await payment_repository.get(refund.payment_id)
    assert payment is not None  # the payment this refund belongs to cannot have been deleted

    merchant_account_id = await ledger.ledger_client.get_system_account(
        "MERCHANT_SETTLEMENT", payment.currency
    )
    if merchant_account_id is None:
        # Unreachable, or a currency with no seeded settlement account
        # (shouldn't happen for a currency that already has a captured
        # payment) — leave PENDING either way; the recovery worker
        # retries the lookup.
        return refund

    posting_result = await ledger.ledger_client.create_posting(
        source_service="payment-service",
        source_id=str(refund.id),
        type="REFUND",
        currency=payment.currency,
        entries=[
            {
                "account_id": str(merchant_account_id),
                "direction": "DEBIT",
                "amount_minor": refund.amount_minor,
            },
            {
                "account_id": str(payment.source_wallet_id),
                "direction": "CREDIT",
                "amount_minor": refund.amount_minor,
            },
        ],
    )

    if posting_result.outcome == PostingOutcome.UNKNOWN:
        return refund

    if posting_result.outcome == PostingOutcome.BUSINESS_REJECTION:
        await refund_repository.transition_status(
            refund.id,
            expected=RefundStatus.PENDING,
            new_status=RefundStatus.FAILED,
            failure_reason=posting_result.failure_reason,
        )
        await session.commit()
        await session.refresh(refund)
        return refund

    # SUCCESS — the money has moved. Recording that against the
    # payment's running total and updating its status happens in the
    # same transaction as marking the refund COMPLETED, but if two
    # refunds for the same payment somehow race past their own
    # (already-checked) eligibility validation at the same instant, the
    # payments.ck_payments_refunded_amount_within_bounds CHECK
    # constraint is the actual last line of defense (spec Section 11:
    # "total refunds <= captured amount") — a violation here means the
    # posting genuinely succeeded but this bookkeeping update didn't,
    # which is a real incident to investigate, not something silently
    # swallowed.
    applied = await refund_repository.transition_status(
        refund.id, expected=RefundStatus.PENDING, new_status=RefundStatus.COMPLETED
    )
    if applied:
        try:
            await payment_repository.add_refunded_amount(payment.id, refund.amount_minor)
        except IntegrityError:
            await session.rollback()
            logger.error(
                "refund %s posted successfully but exceeded payment %s's refundable amount; "
                "payment bookkeeping is now out of sync with the ledger and needs investigation",
                refund.id,
                payment.id,
            )
            raise

        updated_payment = await payment_repository.get(payment.id)
        assert updated_payment is not None
        new_payment_status = (
            PaymentStatus.REFUNDED
            if updated_payment.refunded_amount_minor >= updated_payment.amount_minor
            else PaymentStatus.PARTIALLY_REFUNDED
        )
        await payment_repository.transition_status(
            payment.id, expected=updated_payment.status, new_status=new_payment_status
        )
        session.add(
            payment_outbox_event(
                updated_payment, EventType.PAYMENT_REFUNDED, status=new_payment_status
            )
        )

    await session.commit()
    await session.refresh(refund)
    return refund
