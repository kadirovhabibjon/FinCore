from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.fraud_check import FraudCheck
from app.services.rules import RiskContext, RiskEngine


async def _get_existing(
    session: AsyncSession, *, operation_id: UUID, operation_type: str
) -> FraudCheck | None:
    result = await session.execute(
        select(FraudCheck).where(
            FraudCheck.operation_id == operation_id,
            FraudCheck.operation_type == operation_type,
        )
    )
    return result.scalar_one_or_none()


async def perform_risk_check(
    session: AsyncSession,
    engine: RiskEngine,
    *,
    operation_id: UUID,
    operation_type: str,
    user_id: UUID,
    amount_minor: int,
    currency: str,
) -> FraudCheck:
    """Idempotent on `(operation_id, operation_type)` (spec Section 9.2):
    a retried risk check for the same operation returns the stored
    result instead of re-scoring — which also keeps the frequency-based
    rules' own history lookups from double-counting a retry as two
    separate operations. The UNIQUE constraint, not this pre-check, is
    what actually decides a race between two concurrent first-time
    checks for the same operation (this project's "let the database
    decide" pattern, used throughout).
    """
    existing = await _get_existing(
        session, operation_id=operation_id, operation_type=operation_type
    )
    if existing is not None:
        return existing

    context = RiskContext(
        user_id=user_id,
        amount_minor=amount_minor,
        currency=currency,
        operation_type=operation_type,
        operation_id=operation_id,
    )
    result = await engine.score(session, context)

    check = FraudCheck(
        operation_id=operation_id,
        operation_type=operation_type,
        user_id=user_id,
        amount_minor=amount_minor,
        currency=currency,
        score=result.score,
        decision=result.decision,
        rules_triggered=result.rules_triggered,
    )
    session.add(check)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await _get_existing(
            session, operation_id=operation_id, operation_type=operation_type
        )
        if existing is None:
            raise
        return existing

    await session.refresh(check)
    return check
