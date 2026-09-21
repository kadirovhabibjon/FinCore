import hashlib
import hmac
import time


def build_signature_header(secret: str, *, timestamp: int, body: bytes) -> str:
    """HMAC-SHA256 over `timestamp.body` (spec Section 17: "signed
    requests — HMAC-SHA256 over timestamp + body, header with timestamp
    to prevent replay"). The timestamp is folded into the signed
    material itself, not just sent alongside it — a receiver that
    verifies both (this format lets it) rejects a captured request
    replayed later, not just one with a missing header.

    Format follows Stripe's `Stripe-Signature` convention
    (`t=<ts>,v1=<hex>`): a receiver can extract `t` without parsing hex
    first, and `v1` versions the scheme for a future algorithm change.
    """
    signed_payload = f"{timestamp}.".encode() + body
    digest = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def current_timestamp() -> int:
    return int(time.time())


def verify_signature_header(
    secret: str, *, header: str, body: bytes, tolerance_seconds: int = 300
) -> bool:
    """Reference verifier (used by this service's own tests, and as
    documentation for what a merchant's receiver should implement):
    recomputes the HMAC and rejects a timestamp too far in the past —
    the actual replay defense, since a captured request's signature is
    otherwise valid forever.
    """
    parts = dict(part.split("=", 1) for part in header.split(",") if "=" in part)
    try:
        timestamp = int(parts["t"])
        signature = parts["v1"]
    except (KeyError, ValueError):
        return False

    if abs(current_timestamp() - timestamp) > tolerance_seconds:
        return False

    expected = build_signature_header(secret, timestamp=timestamp, body=body)
    expected_signature = expected.split("v1=", 1)[1]
    return hmac.compare_digest(expected_signature, signature)
