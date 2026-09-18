import random
from dataclasses import dataclass
from datetime import datetime

from fincore_common import EventEnvelope

from app.services.messages import UnhandledEventTypeError

# Errors that will never succeed no matter how many times the same
# event is retried — the producer sent something this consumer can't
# make sense of. Anything not in this tuple is treated as transient
# (spec Section 16: "permanent vs temporary failures — validation error
# -> DLT immediately; timeout -> retry").
_PERMANENT_ERROR_TYPES: tuple[type[Exception], ...] = (
    UnhandledEventTypeError,
    KeyError,
    ValueError,
)


def is_permanent(exc: Exception) -> bool:
    return isinstance(exc, _PERMANENT_ERROR_TYPES)


@dataclass(frozen=True)
class RetryPolicy:
    """Exponential backoff with jitter (spec Section 16). Jitter exists
    so a burst of messages that fail at the same moment (e.g. a provider
    outage) don't all retry in lockstep and hit it again simultaneously.
    """

    max_attempts: int = 3
    base_delay_seconds: float = 2.0
    backoff_factor: float = 2.0
    jitter_ratio: float = 0.2

    def delay_seconds(self, attempt: int) -> float:
        """`attempt` is 1-indexed: the delay before retry number
        `attempt`. Never negative even at the largest jitter draw.
        """
        base = self.base_delay_seconds * (self.backoff_factor ** (attempt - 1))
        jitter = base * self.jitter_ratio
        return max(0.0, base + random.uniform(-jitter, jitter))


def wrap_for_retry(
    original: EventEnvelope, *, attempt: int, not_before: datetime, last_error: str
) -> EventEnvelope:
    """Packs `original` plus retry bookkeeping into a new `EventEnvelope`
    for the retry topic (spec Section 16). Reuses `EventEnvelope` /
    `EventProducer` / `EventConsumer` as-is instead of inventing a
    second wire format — `fincore_common.events` already treats `data`
    as producer-defined per `event_type`, and this convention (used only
    between this service's own main and retry consumer loops) is exactly
    that: private to this producer.
    """
    return EventEnvelope(
        event_id=original.event_id,
        event_type=original.event_type,
        producer="notification-service",
        correlation_id=original.correlation_id,
        data={
            "retry_attempt": attempt,
            "retry_not_before": not_before.isoformat(),
            "retry_last_error": last_error,
            "original_data": original.data,
            "original_producer": original.producer,
        },
    )


def unwrap_retry(envelope: EventEnvelope) -> tuple[EventEnvelope, int, datetime, str]:
    """The inverse of `wrap_for_retry` — recovers the original event
    plus its retry state, for the retry-topic consumer loop
    (app/main.py).
    """
    data = envelope.data
    original = EventEnvelope(
        event_id=envelope.event_id,
        event_type=envelope.event_type,
        producer=data["original_producer"],
        correlation_id=envelope.correlation_id,
        data=data["original_data"],
    )
    attempt = int(data["retry_attempt"])
    not_before = datetime.fromisoformat(data["retry_not_before"])
    last_error = str(data["retry_last_error"])
    return original, attempt, not_before, last_error
