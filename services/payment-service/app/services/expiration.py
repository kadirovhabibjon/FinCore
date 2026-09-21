import logging
from datetime import UTC, datetime, timedelta

from fincore_common import EventType
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.payment import Payment, PaymentStatus
from app.repositories.payment_repository import PaymentRepository
from app.services.payments import payment_outbox_event

logger = logging.getLogger(__name__)


async def expire_stale_payments(
    session: AsyncSession, *, stale_after_seconds: float
) -> list[Payment]:
    """Expires payments stuck in CREATED past their review window (spec
    Section 11: `CREATED -> EXPIRED`) — most likely a fraud REVIEW
    decision nobody ever resolved. No ledger hold exists yet for a
    CREATED payment (one is only reserved once the saga reaches
    PROCESSING), so there's nothing to release here; a payment stuck
    PROCESSING with an open hold is a *recovery* concern instead
    (`app/services/recovery.py`), not an expiration one — the spec's own
    state machine only allows `EXPIRED` from `CREATED`, never from
    `PROCESSING`.
    """
    repository = PaymentRepository(session)
    threshold = datetime.now(UTC) - timedelta(seconds=stale_after_seconds)
    stale_payments = await repository.list_stale_created(older_than=threshold)

    expired: list[Payment] = []
    for payment in stale_payments:
        logger.info("expiration worker expiring stale payment %s", payment.id)
        applied = await repository.transition_status(
            payment.id,
            expected=PaymentStatus.CREATED,
            new_status=PaymentStatus.EXPIRED,
            failure_reason="expired awaiting review",
        )
        if applied:
            session.add(
                payment_outbox_event(
                    payment,
                    EventType.PAYMENT_FAILED,
                    status=PaymentStatus.EXPIRED,
                    failure_reason="expired awaiting review",
                )
            )
            await session.commit()
            await session.refresh(payment)
            expired.append(payment)
    return expired
