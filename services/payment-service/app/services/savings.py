"""Savings goals: money moved out of a wallet and set aside, and back.

Each movement is one posting between the customer's wallet and the
currency's pooled SAVINGS account (ADR-0010), and one row here that
says which goal it was for. The goal's own figure, `saved_minor`,
changes only in the transaction that settles the movement:

  DEPOSIT   posted first; the goal grows when the posting is confirmed.
  WITHDRAW  the goal shrinks first, in the transaction that records the
            movement (`UPDATE ... WHERE saved_minor >= :amount` - two
            withdrawals at once cannot both take the last of it), then
            the posting is made; if the ledger refuses, the amount goes
            back to the goal.

So a goal never shows money that isn't in the pool, and never offers
money already on its way out.

An unanswered posting leaves the movement PENDING - never FAILED, since
the money may have moved - and the recovery worker asks again: the
posting is idempotent on the movement's id, and settling is an atomic
compare-and-set on the status, so asking twice settles once.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.savings import MovementDirection, MovementStatus, SavingsGoal, SavingsMovement
from app.services import ledger
from app.services.ledger import PostingOutcome

logger = logging.getLogger(__name__)

_SERVICE = "payment-service"
# The failure reason of a withdrawal the goal couldn't cover. Worded
# like the API's error titles, as the other failure reasons are.
INSUFFICIENT = "Insufficient Savings"
# ...and of a deposit into a goal closed a moment before it arrived.
CLOSED = "Savings Goal Not Found"


@dataclass(frozen=True)
class MoveInput:
    goal: SavingsGoal
    wallet_id: UUID
    pool_account_id: UUID
    direction: MovementDirection
    amount_minor: int
    idempotency_key_id: UUID


async def start(session: AsyncSession, data: MoveInput) -> SavingsMovement:
    """Records a movement and carries it as far as it will go now.
    Returns normally in every state: COMPLETED, FAILED (nothing lost),
    or PENDING if ledger-service did not answer."""
    movement = SavingsMovement(
        goal_id=data.goal.id,
        owner_user_id=data.goal.owner_user_id,
        wallet_id=data.wallet_id,
        pool_account_id=data.pool_account_id,
        direction=data.direction,
        amount_minor=data.amount_minor,
        currency=data.goal.currency,
        idempotency_key_id=data.idempotency_key_id,
    )
    if data.direction is MovementDirection.WITHDRAW:
        # Take it off the goal now, in the transaction that records the
        # withdrawal, and only if it is there.
        reserved = await session.execute(
            update(SavingsGoal)
            .where(
                SavingsGoal.id == data.goal.id,
                SavingsGoal.closed_at.is_(None),
                SavingsGoal.saved_minor >= data.amount_minor,
            )
            .values(saved_minor=SavingsGoal.saved_minor - data.amount_minor)
        )
        if not reserved.rowcount:  # type: ignore[attr-defined]
            # Recorded, not refused: by now the request has its
            # idempotency key, and a retry must get this same answer.
            movement.status = MovementStatus.FAILED
            movement.failure_reason = INSUFFICIENT
            session.add(movement)
            await session.commit()
            await session.refresh(movement)
            return movement
    else:
        # Hold the goal's row while the deposit is recorded, so closing
        # it (which takes the same lock) either sees this deposit on its
        # way or has already happened - never closes over arriving money.
        locked = await session.execute(
            select(SavingsGoal.closed_at).where(SavingsGoal.id == data.goal.id).with_for_update()
        )
        if locked.scalar_one() is not None:
            movement.status = MovementStatus.FAILED
            movement.failure_reason = CLOSED
            session.add(movement)
            await session.commit()
            await session.refresh(movement)
            return movement
    session.add(movement)
    await session.commit()
    await session.refresh(movement)
    return await advance(session, movement)


async def advance(session: AsyncSession, movement: SavingsMovement) -> SavingsMovement:
    """Makes the movement's posting and settles it. Safe to call again
    at any point, by anyone."""
    await session.refresh(movement)
    if movement.status is not MovementStatus.PENDING:
        return movement

    deposit = movement.direction is MovementDirection.DEPOSIT
    debit, credit = (
        (movement.wallet_id, movement.pool_account_id)
        if deposit
        else (movement.pool_account_id, movement.wallet_id)
    )
    result = await ledger.ledger_client.create_posting(
        source_service=_SERVICE,
        source_id=f"{movement.id}:move",
        type="SAVINGS",
        currency=movement.currency,
        entries=[
            {"account_id": str(debit), "direction": "DEBIT", "amount_minor": movement.amount_minor},
            {
                "account_id": str(credit),
                "direction": "CREDIT",
                "amount_minor": movement.amount_minor,
            },
        ],
    )
    if result.outcome == PostingOutcome.UNKNOWN:
        return movement

    succeeded = result.outcome == PostingOutcome.SUCCESS
    settled = await session.execute(
        update(SavingsMovement)
        .where(
            SavingsMovement.id == movement.id, SavingsMovement.status == MovementStatus.PENDING
        )
        .values(
            status=MovementStatus.COMPLETED if succeeded else MovementStatus.FAILED,
            failure_reason=None if succeeded else result.failure_reason,
            completed_at=datetime.now(UTC) if succeeded else None,
        )
    )
    # Whoever settles it (this call, or one racing it) moves the goal's
    # figure, once: a deposit that arrived adds to it; a withdrawal that
    # was refused gives back what it had taken.
    if settled.rowcount and succeeded == deposit:  # type: ignore[attr-defined]
        await session.execute(
            update(SavingsGoal)
            .where(SavingsGoal.id == movement.goal_id)
            .values(saved_minor=SavingsGoal.saved_minor + movement.amount_minor)
        )
    await session.commit()
    await session.refresh(movement)
    return movement


async def resolve_stuck(
    session: AsyncSession, *, stuck_after_seconds: float
) -> list[SavingsMovement]:
    """Movements left PENDING by an unanswered posting (a request still
    in flight is left alone): each is asked about again."""
    threshold = datetime.now(UTC) - timedelta(seconds=stuck_after_seconds)
    result = await session.execute(
        select(SavingsMovement)
        .where(
            SavingsMovement.status == MovementStatus.PENDING,
            SavingsMovement.updated_at < threshold,
        )
        .order_by(SavingsMovement.updated_at)
    )
    resolved = []
    for movement in result.scalars().all():
        logger.info("recovery worker continuing savings movement %s", movement.id)
        resolved.append(await advance(session, movement))
    return resolved


async def close(session: AsyncSession, goal: SavingsGoal) -> bool:
    """Closes an empty goal with nothing on its way in or out. Under the
    goal's row lock, which a deposit being recorded also takes, so money
    arriving at the same moment can't be closed over. Returns whether
    it closed (False: not empty, or already closed)."""
    locked = await session.execute(
        select(SavingsGoal).where(SavingsGoal.id == goal.id).with_for_update()
    )
    current = locked.scalar_one()
    await session.refresh(current)
    in_flight = await session.execute(
        select(SavingsMovement.id)
        .where(
            SavingsMovement.goal_id == goal.id, SavingsMovement.status == MovementStatus.PENDING
        )
        .limit(1)
    )
    if (
        current.closed_at is not None
        or current.saved_minor != 0
        or in_flight.scalar_one_or_none() is not None
    ):
        await session.rollback()
        return False
    current.closed_at = datetime.now(UTC)
    await session.commit()
    return True
