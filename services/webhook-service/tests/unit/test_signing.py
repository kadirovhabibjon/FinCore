from app.services.signing import build_signature_header, verify_signature_header


def test_verifier_accepts_a_freshly_built_signature() -> None:
    secret = "test-secret"
    body = b'{"event_id":"abc","status":"SUCCESS"}'
    header = build_signature_header(secret, timestamp=1_700_000_000, body=body)

    # A generous tolerance since this fixed timestamp isn't "now" —
    # what matters here is the HMAC itself matches, not the clock.
    assert verify_signature_header(
        secret, header=header, body=body, tolerance_seconds=10**12
    )


def test_verifier_rejects_a_tampered_body() -> None:
    secret = "test-secret"
    header = build_signature_header(secret, timestamp=1_700_000_000, body=b"original")

    assert not verify_signature_header(
        secret, header=header, body=b"tampered", tolerance_seconds=10**12
    )


def test_verifier_rejects_the_wrong_secret() -> None:
    body = b"payload"
    header = build_signature_header("secret-a", timestamp=1_700_000_000, body=body)

    assert not verify_signature_header(
        "secret-b", header=header, body=body, tolerance_seconds=10**12
    )


def test_verifier_rejects_a_stale_timestamp() -> None:
    secret = "test-secret"
    body = b"payload"
    header = build_signature_header(secret, timestamp=1_700_000_000, body=body)

    assert not verify_signature_header(secret, header=header, body=body, tolerance_seconds=300)


def test_verifier_rejects_a_malformed_header() -> None:
    assert not verify_signature_header("secret", header="garbage", body=b"x")
    assert not verify_signature_header("secret", header="t=notanumber,v1=abc", body=b"x")
