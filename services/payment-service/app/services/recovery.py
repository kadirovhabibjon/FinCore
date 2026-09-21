import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.payment import Payment
from app.domain.refund import Refund
from app.domain.transfer import Transfer
from app.repositories.payment_repository import PaymentRepository
from app.repositories.refund_repository import RefundRepository
from app.repositories.transfer_repository import TransferRepository
from app.services.payments import attempt_hold_and_capture
from app.services.refunds import attempt_refund_posting
from app.services.transfers import attempt_posting_and_resolve

logger = logging.getLogger(__name__)


async def resolve_stuck_transfers(
    session: AsyncSession, *, stuck_after_seconds: float
) -> list[Transfer]:
    """Finds transfers left in PROCESSING by an unknown ledger outcome
    (spec Section 10.1) and retries the posting for each, exactly as the
    saga would have continued had the original call not timed out.

    A transfer only counts as stuck once it has sat in PROCESSING for
    `stuck_after_seconds` — a transfer whose original request is still
    genuinely in flight is left alone rather than raced.
    """
    repository = TransferRepository(session)
    threshold = datetime.now(UTC) - timedelta(seconds=stuck_after_seconds)
    stuck_transfers = await repository.list_stuck_processing(older_than=threshold)

    resolved: list[Transfer] = []
    for transfer in stuck_transfers:
        logger.info("recovery worker retrying stuck transfer %s", transfer.id)
        resolved.append(await attempt_posting_and_resolve(session, repository, transfer))
    return resolved


async def resolve_stuck_payments(
    session: AsyncSession, *, stuck_after_seconds: float
) -> list[Payment]:
    """Same idea as `resolve_stuck_transfers`, for payments left in
    PROCESSING by an unknown hold-creation or capture outcome (spec
    Section 11) — retries whichever of the two steps hasn't succeeded
    yet, exactly as the saga would have continued.
    """
    repository = PaymentRepository(session)
    threshold = datetime.now(UTC) - timedelta(seconds=stuck_after_seconds)
    stuck_payments = await repository.list_stuck_processing(older_than=threshold)

    resolved: list[Payment] = []
    for payment in stuck_payments:
        logger.info("recovery worker retrying stuck payment %s", payment.id)
        resolved.append(await attempt_hold_and_capture(session, repository, payment))
    return resolved


async def resolve_stuck_refunds(
    session: AsyncSession, *, stuck_after_seconds: float
) -> list[Refund]:
    """Same idea again, for refunds left PENDING by an unknown posting
    outcome (spec Section 11).
    """
    threshold = datetime.now(UTC) - timedelta(seconds=stuck_after_seconds)
    stuck_refunds = await RefundRepository(session).list_stuck_pending(older_than=threshold)

    resolved: list[Refund] = []
    for refund in stuck_refunds:
        logger.info("recovery worker retrying stuck refund %s", refund.id)
        resolved.append(await attempt_refund_posting(session, refund))
    return resolved
