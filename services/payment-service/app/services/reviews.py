"""Resolving fraud REVIEW decisions (ADR-0005's admin panel).

A REVIEW leaves a transfer PENDING or a payment CREATED with no ledger
effect yet (spec Sections 10.1 and 11). A reviewer's decision picks up
the saga exactly where the fraud check left it:

  approve -> PROCESSING, then the same ledger step an ALLOW would have run
  reject  -> FAILED, with the usual *.failed outbox event

The claim is one atomic UPDATE (`resolve_review`), so a second reviewer,
or the payment expiration worker, racing on the same item loses cleanly
instead of running the saga twice.
"""

import enum
from datetime import UTC, datetime
from uuid import UUID

from fincore_common import EventType
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ReviewAlreadyResolvedError, ReviewNotFoundError
from app.domain.payment import Payment, PaymentStatus
from app.domain.transfer import Transfer, TransferStatus
from app.repositories.payment_repository import PaymentRepository
from app.repositories.transfer_repository import TransferRepository
from app.services.payments import attempt_hold_and_capture, payment_outbox_event
from app.services.transfers import attempt_posting_and_resolve, transfer_outbox_event

REJECTED_REASON = "rejected in fraud review"


class ReviewDecision(enum.StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


async def resolve_review(
    session: AsyncSession, *, operation_id: UUID, reviewer_id: UUID, decision: ReviewDecision
) -> Transfer | Payment:
    transfer = await TransferRepository(session).get(operation_id)
    if transfer is not None:
        return await _resolve_transfer(session, transfer, reviewer_id, decision)

    payment = await PaymentRepository(session).get(operation_id)
    if payment is not None:
        return await _resolve_payment(session, payment, reviewer_id, decision)

    raise ReviewNotFoundError(str(operation_id))


async def _resolve_transfer(
    session: AsyncSession, transfer: Transfer, reviewer_id: UUID, decision: ReviewDecision
) -> Transfer:
    repository = TransferRepository(session)
    now = datetime.now(UTC)

    if decision == ReviewDecision.REJECT:
        claimed = await repository.resolve_review(
            transfer.id,
            new_status=TransferStatus.FAILED,
            reviewer_id=reviewer_id,
            reviewed_at=now,
            failure_reason=REJECTED_REASON,
        )
        if not claimed:
            raise ReviewAlreadyResolvedError(str(transfer.id))
        session.add(
            transfer_outbox_event(
                transfer,
                EventType.TRANSFER_FAILED,
                status=TransferStatus.FAILED,
                failure_reason=REJECTED_REASON,
            )
        )
        await session.commit()
        await session.refresh(transfer)
        return transfer

    claimed = await repository.resolve_review(
        transfer.id,
        new_status=TransferStatus.PROCESSING,
        reviewer_id=reviewer_id,
        reviewed_at=now,
    )
    if not claimed:
        raise ReviewAlreadyResolvedError(str(transfer.id))
    await session.commit()
    await session.refresh(transfer)
    return await attempt_posting_and_resolve(session, repository, transfer)


async def _resolve_payment(
    session: AsyncSession, payment: Payment, reviewer_id: UUID, decision: ReviewDecision
) -> Payment:
    repository = PaymentRepository(session)
    now = datetime.now(UTC)

    if decision == ReviewDecision.REJECT:
        claimed = await repository.resolve_review(
            payment.id,
            new_status=PaymentStatus.FAILED,
            reviewer_id=reviewer_id,
            reviewed_at=now,
            failure_reason=REJECTED_REASON,
        )
        if not claimed:
            raise ReviewAlreadyResolvedError(str(payment.id))
        session.add(
            payment_outbox_event(
                payment,
                EventType.PAYMENT_FAILED,
                status=PaymentStatus.FAILED,
                failure_reason=REJECTED_REASON,
            )
        )
        await session.commit()
        await session.refresh(payment)
        return payment

    claimed = await repository.resolve_review(
        payment.id,
        new_status=PaymentStatus.PROCESSING,
        reviewer_id=reviewer_id,
        reviewed_at=now,
    )
    if not claimed:
        raise ReviewAlreadyResolvedError(str(payment.id))
    await session.commit()
    await session.refresh(payment)
    return await attempt_hold_and_capture(session, repository, payment)
