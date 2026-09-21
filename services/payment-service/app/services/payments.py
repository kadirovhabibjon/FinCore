from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from fincore_common import EventType, get_correlation_id
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domain.outbox import OutboxEvent
from app.domain.payment import Payment, PaymentStatus
from app.domain.transfer import FraudDecision
from app.repositories.payment_repository import PaymentRepository
from app.services import fraud, ledger
from app.services.ledger import HoldOutcome, PostingOutcome


def payment_outbox_event(
    payment: Payment,
    event_type: EventType,
    *,
    status: PaymentStatus,
    failure_reason: str | None = None,
    completed_at: datetime | None = None,
) -> OutboxEvent:
    """Built from the values this call is about to (or just did) write,
    not by re-reading `payment` — same reasoning as
    transfers.py's `_transfer_outbox_event`.
    """
    return OutboxEvent(
        aggregate_type="Payment",
        aggregate_id=str(payment.id),
        event_type=event_type.value,
        correlation_id=get_correlation_id(),
        payload={
            "payment_id": str(payment.id),
            "reference": payment.reference,
            "initiator_user_id": str(payment.initiator_user_id),
            "merchant_id": str(payment.merchant_id),
            "amount_minor": payment.amount_minor,
            "currency": payment.currency,
            "status": status.value,
            "failure_reason": failure_reason,
            "completed_at": completed_at.isoformat() if completed_at else None,
        },
    )


@dataclass(frozen=True)
class CreatePaymentInput:
    initiator_user_id: UUID
    idempotency_key_id: UUID
    source_wallet_id: UUID
    merchant_id: UUID
    amount_minor: int
    currency: str
    description: str | None = None


async def create_payment(session: AsyncSession, data: CreatePaymentInput) -> Payment:
    """Creates a Payment and runs its saga to its first stopping point
    (spec Section 11):

      fraud BLOCK               -> FAILED
      fraud REVIEW               -> stays CREATED
      fraud unreachable          -> fail-open/fail-closed policy decides (app/services/fraud.py)
      hold + capture succeed     -> SUCCESS
      hold/capture business-rejected -> FAILED (e.g. insufficient funds)
      hold/capture outcome unknown   -> stays PROCESSING (recovery worker resolves it)

    Every branch returns normally — landing in any of these states is
    the saga working correctly for that outcome, not this function
    failing.
    """
    payment = Payment(
        initiator_user_id=data.initiator_user_id,
        source_wallet_id=data.source_wallet_id,
        merchant_id=data.merchant_id,
        amount_minor=data.amount_minor,
        currency=data.currency,
        description=data.description,
        idempotency_key_id=data.idempotency_key_id,
    )
    session.add(payment)
    await session.commit()
    await session.refresh(payment)

    return await _advance_payment_saga(session, payment)


async def _advance_payment_saga(session: AsyncSession, payment: Payment) -> Payment:
    repository = PaymentRepository(session)

    fraud_result = await fraud.fraud_client.check(
        user_id=payment.initiator_user_id,
        amount_minor=payment.amount_minor,
        currency=payment.currency,
        operation_type="PAYMENT",
        operation_id=payment.id,
    )

    if fraud_result.decision == FraudDecision.BLOCK:
        await repository.transition_status(
            payment.id,
            expected=PaymentStatus.CREATED,
            new_status=PaymentStatus.FAILED,
            failure_reason="blocked by fraud check",
            fraud_decision=FraudDecision.BLOCK,
        )
        session.add(
            payment_outbox_event(
                payment,
                EventType.PAYMENT_FAILED,
                status=PaymentStatus.FAILED,
                failure_reason="blocked by fraud check",
            )
        )
        await session.commit()
        await session.refresh(payment)
        return payment

    if fraud_result.decision == FraudDecision.REVIEW:
        await repository.transition_status(
            payment.id,
            expected=PaymentStatus.CREATED,
            new_status=PaymentStatus.CREATED,
            fraud_decision=FraudDecision.REVIEW,
        )
        await session.commit()
        await session.refresh(payment)
        return payment

    # ALLOW: CREATED -> PROCESSING, then attempt the hold + capture.
    await repository.transition_status(
        payment.id,
        expected=PaymentStatus.CREATED,
        new_status=PaymentStatus.PROCESSING,
        fraud_decision=FraudDecision.ALLOW,
    )
    await session.commit()
    await session.refresh(payment)

    return await attempt_hold_and_capture(session, repository, payment)


async def attempt_hold_and_capture(
    session: AsyncSession, repository: PaymentRepository, payment: Payment
) -> Payment:
    """Reserves funds on the source wallet (spec Section 8.4's reserve
    step, skipped if an earlier attempt already recorded `hold_id`) then
    immediately captures the full amount into the currency's
    MERCHANT_SETTLEMENT account — auto-captured within the same saga
    rather than deferred as a separate step, since no API exists (yet)
    to trigger a capture independently of creating the payment.

    Shared by `_advance_payment_saga` (the payment's first attempt) and
    the recovery worker (`app/services/recovery.py`, retrying a payment
    left PROCESSING by an earlier unknown outcome). Safe to call more
    than once: both `create_hold` and `capture_hold` are idempotent on
    `(source_service, source_id)` on ledger-service's side.
    """
    if payment.hold_id is None:
        hold_result = await ledger.ledger_client.create_hold(
            source_service="payment-service",
            source_id=str(payment.id),
            account_id=payment.source_wallet_id,
            amount_minor=payment.amount_minor,
            currency=payment.currency,
            ttl_seconds=settings.payment_hold_ttl_seconds,
        )

        if hold_result.outcome == HoldOutcome.UNKNOWN:
            # Leave PROCESSING, hold_id still unset — the recovery
            # worker retries create_hold, which is safe/idempotent.
            return payment

        if hold_result.outcome == HoldOutcome.BUSINESS_REJECTION:
            applied = await repository.transition_status(
                payment.id,
                expected=PaymentStatus.PROCESSING,
                new_status=PaymentStatus.FAILED,
                failure_reason=hold_result.failure_reason,
            )
            if applied:
                session.add(
                    payment_outbox_event(
                        payment,
                        EventType.PAYMENT_FAILED,
                        status=PaymentStatus.FAILED,
                        failure_reason=hold_result.failure_reason,
                    )
                )
            await session.commit()
            await session.refresh(payment)
            return payment

        assert hold_result.hold_id is not None
        await session.execute(
            update(Payment).where(Payment.id == payment.id).values(hold_id=hold_result.hold_id)
        )
        await session.commit()
        await session.refresh(payment)

    assert payment.hold_id is not None  # guaranteed by the branch above, for mypy's benefit
    posting_result = await ledger.ledger_client.capture_hold(
        payment.hold_id,
        amount_minor=payment.amount_minor,
        source_service="payment-service",
        source_id=str(payment.id),
    )

    if posting_result.outcome == PostingOutcome.UNKNOWN:
        # Leave PROCESSING — the recovery worker retries capture_hold,
        # which is safe/idempotent.
        return payment

    if posting_result.outcome == PostingOutcome.SUCCESS:
        completed_at = datetime.now(UTC)
        applied = await repository.transition_status(
            payment.id,
            expected=PaymentStatus.PROCESSING,
            new_status=PaymentStatus.SUCCESS,
            completed_at=completed_at,
        )
        if applied:
            session.add(
                payment_outbox_event(
                    payment,
                    EventType.PAYMENT_COMPLETED,
                    status=PaymentStatus.SUCCESS,
                    completed_at=completed_at,
                )
            )
        await session.commit()
        await session.refresh(payment)
        return payment

    # BUSINESS_REJECTION — e.g. the hold expired between our two calls.
    # Best-effort release: harmless even if the hold already resolved
    # itself (ledger-service's release is idempotent).
    await ledger.ledger_client.release_hold(payment.hold_id)
    applied = await repository.transition_status(
        payment.id,
        expected=PaymentStatus.PROCESSING,
        new_status=PaymentStatus.FAILED,
        failure_reason=posting_result.failure_reason,
    )
    if applied:
        session.add(
            payment_outbox_event(
                payment,
                EventType.PAYMENT_FAILED,
                status=PaymentStatus.FAILED,
                failure_reason=posting_result.failure_reason,
            )
        )
    await session.commit()
    await session.refresh(payment)
    return payment
