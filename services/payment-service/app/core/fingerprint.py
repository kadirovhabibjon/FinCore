import hashlib
import json


def _canonical_body(body: bytes) -> bytes:
    """Re-serializes a JSON body with sorted keys so two requests that
    differ only in field order produce the same fingerprint. Falls back
    to the raw bytes for a non-JSON (or empty) body.
    """
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return body
    return json.dumps(parsed, sort_keys=True, separators=(",", ":")).encode()


def compute_fingerprint(method: str, path: str, body: bytes) -> str:
    """Spec Section 9.1: "a hash of method + path + canonical body." Used
    to detect an Idempotency-Key being reused for a materially different
    request.
    """
    canonical = f"{method.upper()}\n{path}\n".encode() + _canonical_body(body)
    return hashlib.sha256(canonical).hexdigest()
