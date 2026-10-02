from app.services.rate_limit import SlidingWindowLimiter


def test_allows_up_to_the_limit_per_window_and_per_key() -> None:
    limiter = SlidingWindowLimiter(limit=2, window_seconds=60)

    assert limiter.allow("a", now=0)
    assert limiter.allow("a", now=1)
    assert not limiter.allow("a", now=2)
    assert limiter.allow("b", now=2)  # other customers unaffected
    assert limiter.allow("a", now=61)  # the first hit has left the window
