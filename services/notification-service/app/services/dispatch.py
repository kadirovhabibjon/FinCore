import asyncio
import logging
from datetime import UTC, datetime, timedelta

from fincore_common import EventEnvelope
from fincore_common.kafka import EventProducer

from app.db import session as db_session
from app.domain.dead_letter import DeadLetter
from app.services.consumer import handle_transfer_event
from app.services.providers import NotificationProvider
from app.services.retry import RetryPolicy, is_permanent, unwrap_retry, wrap_for_retry

logger = logging.getLogger(__name__)


async def process_with_retry_routing(
    envelope: EventEnvelope,
    *,
    attempt: int,
    providers: list[NotificationProvider],
    side_channel_producer: EventProducer,
    retry_topic: str,
    dlt_topic: str,
    policy: RetryPolicy,
) -> None:
    """Attempts `handle_transfer_event` once. On failure, routes the
    event onward instead of letting the exception propagate and block
    whichever Kafka partition called this (spec Section 16 — "retry
    topics vs blocking retries: why blocking a partition is dangerous"):

      permanent error                -> straight to the DLT
      transient error, attempts left -> the retry topic, delayed
      transient error, exhausted     -> the DLT

    Never raises — the caller (the main or retry consumer loop,
    app/main.py) always gets to commit its own offset and move on to
    the next message, which is the entire point of routing instead of
    blocking.
    """
    try:
        await handle_transfer_event(envelope, providers)
        return
    except Exception as exc:
        logger.warning("event %s failed on attempt %d: %s", envelope.event_id, attempt, exc)
        if is_permanent(exc) or attempt >= policy.max_attempts:
            await _dead_letter(envelope, dlt_topic, side_channel_producer, str(exc), attempt)
            return

        next_attempt = attempt + 1
        retry_envelope = wrap_for_retry(
            envelope,
            attempt=next_attempt,
            not_before=datetime.now(UTC) + timedelta(seconds=policy.delay_seconds(next_attempt)),
            last_error=str(exc),
        )
        await side_channel_producer.send(
            retry_topic, key=str(envelope.event_id), envelope=retry_envelope
        )


async def process_retry_topic_message(
    envelope: EventEnvelope,
    *,
    providers: list[NotificationProvider],
    side_channel_producer: EventProducer,
    retry_topic: str,
    dlt_topic: str,
    policy: RetryPolicy,
) -> None:
    """Handler for the retry topic's consumer loop (app/main.py).
    Unwraps the original event and its retry state, waits out whatever
    is left of its backoff — delaying only this topic's own partition,
    never the main "transfers" one — then re-attempts it through the
    same routing decision as the first attempt.
    """
    original, attempt, not_before, _ = unwrap_retry(envelope)
    remaining = (not_before - datetime.now(UTC)).total_seconds()
    if remaining > 0:
        await asyncio.sleep(remaining)

    await process_with_retry_routing(
        original,
        attempt=attempt,
        providers=providers,
        side_channel_producer=side_channel_producer,
        retry_topic=retry_topic,
        dlt_topic=dlt_topic,
        policy=policy,
    )


async def _dead_letter(
    envelope: EventEnvelope,
    topic: str,
    producer: EventProducer,
    error: str,
    attempts: int,
) -> None:
    logger.error(
        "dead-lettering event %s after %d attempt(s): %s", envelope.event_id, attempts, error
    )
    async with db_session.async_session_factory() as session:
        session.add(
            DeadLetter(
                event_id=envelope.event_id,
                topic=topic,
                envelope=envelope.model_dump(mode="json"),
                last_error=error,
                attempts=attempts,
            )
        )
        await session.commit()
    # Also published to Kafka, not just recorded in our own DB: a
    # separate alerting/ops consumer could subscribe to this topic
    # later without needing direct DB access to this service.
    await producer.send(topic, key=str(envelope.event_id), envelope=envelope)
