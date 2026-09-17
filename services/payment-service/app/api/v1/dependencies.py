from fastapi import Header, Request

from app.core.fingerprint import compute_fingerprint


async def get_idempotency_fingerprint(
    request: Request,
    idempotency_key: str = Header(
        ..., alias="Idempotency-Key", min_length=1, max_length=128
    ),
) -> tuple[str, str]:
    """Returns (key, fingerprint) for app.services.idempotency. Reads the
    raw body directly (rather than depending on the endpoint's already-
    parsed Pydantic model) so the fingerprint reflects exactly what the
    client sent, byte for byte before Pydantic normalization.
    """
    body = await request.body()
    fingerprint = compute_fingerprint(request.method, request.url.path, body)
    return idempotency_key, fingerprint
