from app.services.retry import RetryPolicy


def test_delay_grows_exponentially_and_stays_within_jitter_bounds() -> None:
    policy = RetryPolicy(base_delay_seconds=5.0, backoff_factor=2.0, jitter_ratio=0.2)

    for attempt in (1, 2, 3, 4):
        base = 5.0 * (2.0 ** (attempt - 1))
        for _ in range(50):
            delay = policy.delay_seconds(attempt)
            assert base * 0.8 <= delay <= base * 1.2


def test_delay_is_never_negative_even_at_maximum_negative_jitter() -> None:
    policy = RetryPolicy(base_delay_seconds=0.1, jitter_ratio=1.0)

    for _ in range(200):
        assert policy.delay_seconds(1) >= 0.0
