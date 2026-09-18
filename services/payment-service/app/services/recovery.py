import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.transfer import Transfer
from app.repositories.transfer_repository import TransferRepository
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
