from datetime import UTC, datetime

from fincore_common import EventEnvelope
from fincore_common.kafka import EventProducer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AlreadyReplayedError
from app.domain.dead_letter import DeadLetter


async def replay_dead_letter(
    session: AsyncSession, dead_letter: DeadLetter, producer: EventProducer, topic: str
) -> None:
    """Manual replay (spec Section 16) — republishes the original event
    onto the main topic so it goes through ordinary processing again,
    then marks this row done. Not idempotent by accident: replaying an
    already-replayed row is rejected rather than silently re-publishing
    a second time.
    """
    if dead_letter.replayed_at is not None:
        raise AlreadyReplayedError(str(dead_letter.id))

    envelope = EventEnvelope.model_validate(dead_letter.envelope)
    await producer.send(topic, key=str(envelope.event_id), envelope=envelope)

    dead_letter.replayed_at = datetime.now(UTC)
    await session.commit()
