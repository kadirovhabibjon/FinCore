import uuid
from datetime import UTC, datetime, timedelta

from fincore_common import EventEnvelope, EventType

from app.services.messages import UnhandledEventTypeError
from app.services.providers import ProviderUnavailableError
from app.services.retry import RetryPolicy, is_permanent, unwrap_retry, wrap_for_retry


def test_permanent_errors_are_classified_as_permanent() -> None:
    assert is_permanent(UnhandledEventTypeError("x"))
    assert is_permanent(KeyError("missing_field"))
    assert is_permanent(ValueError("bad amount"))


def test_provider_errors_are_classified_as_transient() -> None:
    assert not is_permanent(ProviderUnavailableError("timeout"))
    assert not is_permanent(RuntimeError("unexpected"))


def test_delay_grows_exponentially_and_stays_within_jitter_bounds() -> None:
    policy = RetryPolicy(base_delay_seconds=2.0, backoff_factor=2.0, jitter_ratio=0.2)

    for attempt in (1, 2, 3):
        base = 2.0 * (2.0 ** (attempt - 1))
        for _ in range(50):
            delay = policy.delay_seconds(attempt)
            assert base * 0.8 <= delay <= base * 1.2


def test_delay_is_never_negative_even_at_maximum_negative_jitter() -> None:
    policy = RetryPolicy(base_delay_seconds=0.1, jitter_ratio=1.0)

    for _ in range(200):
        assert policy.delay_seconds(1) >= 0.0


def test_wrap_and_unwrap_round_trip() -> None:
    original = EventEnvelope(
        event_type=EventType.TRANSFER_COMPLETED,
        producer="payment-service",
        correlation_id="corr-1",
        data={"transfer_id": str(uuid.uuid4()), "amount_minor": 100},
    )
    not_before = datetime.now(UTC) + timedelta(seconds=5)

    wrapped = wrap_for_retry(original, attempt=2, not_before=not_before, last_error="boom")

    assert wrapped.event_id == original.event_id
    assert wrapped.producer == "notification-service"

    recovered, attempt, recovered_not_before, last_error = unwrap_retry(wrapped)

    assert recovered.event_id == original.event_id
    assert recovered.producer == "payment-service"
    assert recovered.data == original.data
    assert recovered.correlation_id == original.correlation_id
    assert attempt == 2
    assert last_error == "boom"
    assert abs((recovered_not_before - not_before).total_seconds()) < 0.001
