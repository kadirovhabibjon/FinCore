from app.core.fingerprint import compute_fingerprint


def test_same_request_produces_the_same_fingerprint() -> None:
    body = b'{"amount": "100.00", "currency": "UZS"}'

    first = compute_fingerprint("POST", "/api/v1/transfers", body)
    second = compute_fingerprint("POST", "/api/v1/transfers", body)

    assert first == second


def test_different_bodies_produce_different_fingerprints() -> None:
    a = compute_fingerprint("POST", "/api/v1/transfers", b'{"amount": "100.00"}')
    b = compute_fingerprint("POST", "/api/v1/transfers", b'{"amount": "200.00"}')

    assert a != b


def test_key_order_does_not_affect_the_fingerprint() -> None:
    a = compute_fingerprint("POST", "/api/v1/transfers", b'{"amount": "100.00", "currency": "UZS"}')
    b = compute_fingerprint("POST", "/api/v1/transfers", b'{"currency": "UZS", "amount": "100.00"}')

    assert a == b


def test_different_paths_produce_different_fingerprints() -> None:
    a = compute_fingerprint("POST", "/api/v1/transfers", b"{}")
    b = compute_fingerprint("POST", "/api/v1/payments", b"{}")

    assert a != b


def test_different_methods_produce_different_fingerprints() -> None:
    a = compute_fingerprint("POST", "/api/v1/transfers", b"{}")
    b = compute_fingerprint("GET", "/api/v1/transfers", b"{}")

    assert a != b


def test_non_json_body_does_not_raise() -> None:
    # Falls back to raw bytes rather than crashing on non-JSON input.
    compute_fingerprint("POST", "/api/v1/transfers", b"not json at all")
