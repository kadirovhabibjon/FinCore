from datetime import UTC, datetime, timedelta
from typing import Any, NoReturn
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import IdempotencyKeyConflictError, IdempotencyKeyInProgressError
from app.domain.idempotency import IdempotencyKey, IdempotencyKeyStatus
from app.repositories.idempotency_repository import IdempotencyKeyRepository

_DEFAULT_TTL_SECONDS = 24 * 60 * 60  # 24h, per spec Section 9.1's example


class IdempotentReplayResponse(Exception):
    """Not an error: raised to short-circuit a request whose
    Idempotency-Key already completed successfully once. An exception
    handler (registered in app/main.py) turns this into the exact stored
    response rather than re-running the business logic.
    """

    def __init__(self, status_code: int, body: dict[str, Any] | None) -> None:
        super().__init__(f"idempotent replay: {status_code}")
        self.status_code = status_code
        self.body = body


async def begin_idempotent_request(
    session: AsyncSession,
    *,
    user_id: UUID,
    key: str,
    fingerprint: str,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
) -> IdempotencyKey:
    """Call before doing the actual work. Returns an IN_PROGRESS
    IdempotencyKey row the caller should later pass to
    `complete_idempotent_request`.

    - Same key, same fingerprint, COMPLETED -> raises IdempotentReplayResponse
      (caller never re-executes the business logic).
    - Same key, same fingerprint, IN_PROGRESS -> raises
      IdempotencyKeyInProgressError (409): a concurrent request with the
      same key hasn't finished yet.
    - Same key, different fingerprint -> raises IdempotencyKeyConflictError
      (422): the caller is reusing a key for a materially different
      request.
    - Same key, but its TTL has passed -> the row is reset for this new
      attempt in place, rather than inserted fresh: UNIQUE(user_id, key)
      would otherwise block a plain INSERT while the stale row still
      exists, and there is no cleanup job removing expired rows yet.
    - No existing row -> inserted as IN_PROGRESS. The UNIQUE constraint,
      not this pre-check, is what actually decides a race between two
      concurrent first-time requests carrying the same key (Section 9's
      "let the database decide" pattern, used throughout this project).
    """
    repository = IdempotencyKeyRepository(session)
    existing = await repository.get(user_id, key)

    if existing is not None:
        if existing.expires_at < datetime.now(UTC):
            return await _reset_for_reuse(session, existing, fingerprint, ttl_seconds)
        _replay_or_reject(existing, fingerprint)

    record = IdempotencyKey(
        user_id=user_id,
        key=key,
        request_fingerprint=fingerprint,
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
    )
    session.add(record)

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await repository.get(user_id, key)
        if existing is None:
            raise
        if existing.expires_at < datetime.now(UTC):
            return await _reset_for_reuse(session, existing, fingerprint, ttl_seconds)
        _replay_or_reject(existing, fingerprint)

    await session.refresh(record)
    return record


async def complete_idempotent_request(
    session: AsyncSession,
    idempotency_key: IdempotencyKey,
    *,
    status_code: int,
    body: dict[str, Any],
    resource_id: UUID | None = None,
) -> None:
    idempotency_key.status = IdempotencyKeyStatus.COMPLETED
    idempotency_key.response_status_code = status_code
    idempotency_key.response_body = body
    idempotency_key.resource_id = resource_id
    await session.commit()


async def _reset_for_reuse(
    session: AsyncSession,
    existing: IdempotencyKey,
    fingerprint: str,
    ttl_seconds: int,
) -> IdempotencyKey:
    existing.request_fingerprint = fingerprint
    existing.status = IdempotencyKeyStatus.IN_PROGRESS
    existing.response_status_code = None
    existing.response_body = None
    existing.resource_id = None
    existing.expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
    await session.commit()
    await session.refresh(existing)
    return existing


def _replay_or_reject(existing: IdempotencyKey, fingerprint: str) -> NoReturn:
    if existing.request_fingerprint != fingerprint:
        raise IdempotencyKeyConflictError(
            "this Idempotency-Key was already used with a different request"
        )
    if existing.status == IdempotencyKeyStatus.IN_PROGRESS:
        raise IdempotencyKeyInProgressError("a request with this Idempotency-Key is in progress")
    raise IdempotentReplayResponse(existing.response_status_code or 200, existing.response_body)
