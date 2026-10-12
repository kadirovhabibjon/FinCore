from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.encoders import jsonable_encoder
from fincore_common import SUPPORTED_CURRENCIES
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import (
    AuthenticatedUser,
    get_authenticated_user,
    get_idempotency_fingerprint,
)
from app.core.amounts import parse_positive_amount
from app.core.exceptions import (
    CurrencyMismatchError,
    GoalNotEmptyError,
    InvalidAmountError,
    SavingsGoalNotFoundError,
    SavingsUnavailableError,
    TooManySavingsGoalsError,
    WalletNotFoundError,
)
from app.db.session import get_db
from app.domain.savings import MovementDirection, MovementStatus, SavingsGoal, SavingsMovement
from app.services import ledger, savings
from app.services.idempotency import begin_idempotent_request, complete_idempotent_request

router = APIRouter(prefix="/api/v1/savings-goals", tags=["savings"])

# Goals are for a few things one is saving towards, not for bookkeeping.
MAX_GOALS = 20


class CreateGoalRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    currency: str = Field(min_length=3, max_length=3)
    # Decimal string: what the customer is saving up to.
    target: str = Field(min_length=1, max_length=32)

    @field_validator("name")
    @classmethod
    def _one_line(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned


class GoalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    currency: str
    target_minor: int
    # In the goal now (and not already on its way back to a wallet).
    saved_minor: int
    created_at: datetime


class MoveRequest(BaseModel):
    # The caller's wallet the money comes from, or goes back to.
    wallet_id: UUID
    # Decimal string at the API boundary, never a JSON number (ADR-0001).
    amount: str = Field(min_length=1, max_length=32)


class MovementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reference: str
    goal_id: UUID
    wallet_id: UUID
    direction: MovementDirection
    amount_minor: int
    currency: str
    # PENDING: the ledger has not confirmed it yet; it will be settled.
    status: MovementStatus
    failure_reason: str | None
    created_at: datetime
    completed_at: datetime | None


async def _open_goal(session: AsyncSession, goal_id: UUID, user_id: UUID) -> SavingsGoal:
    goal = await session.get(SavingsGoal, goal_id)
    if goal is None or goal.owner_user_id != user_id or goal.closed_at is not None:
        raise SavingsGoalNotFoundError(str(goal_id))
    return goal


@router.get("", response_model=list[GoalResponse])
async def list_my_goals(
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> list[GoalResponse]:
    """The caller's open savings goals, oldest first."""
    result = await session.execute(
        select(SavingsGoal)
        .where(SavingsGoal.owner_user_id == user.user_id, SavingsGoal.closed_at.is_(None))
        .order_by(SavingsGoal.created_at, SavingsGoal.id)
    )
    return [GoalResponse.model_validate(goal) for goal in result.scalars().all()]


@router.post("", response_model=GoalResponse, status_code=status.HTTP_201_CREATED)
async def create_goal(
    payload: CreateGoalRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> GoalResponse:
    """Something to save towards: a name and a target, in one currency.
    Empty until money is put in."""
    if payload.currency not in SUPPORTED_CURRENCIES:
        raise InvalidAmountError(f"unsupported currency {payload.currency}")
    target_minor = parse_positive_amount(payload.target, payload.currency)
    count = await session.execute(
        select(func.count())
        .select_from(SavingsGoal)
        .where(SavingsGoal.owner_user_id == user.user_id, SavingsGoal.closed_at.is_(None))
    )
    if count.scalar_one() >= MAX_GOALS:
        raise TooManySavingsGoalsError(f"at most {MAX_GOALS} goals; close one first")
    goal = SavingsGoal(
        owner_user_id=user.user_id,
        name=payload.name,
        currency=payload.currency,
        target_minor=target_minor,
    )
    session.add(goal)
    await session.commit()
    await session.refresh(goal)
    return GoalResponse.model_validate(goal)


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def close_goal(
    goal_id: UUID,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Closes an empty goal. One with money in it, or on its way in or
    out, is `409 Goal Not Empty`: take the money back first."""
    goal = await _open_goal(session, goal_id, user.user_id)
    if not await savings.close(session, goal):
        raise GoalNotEmptyError("take the money back to a wallet before closing the goal")


async def _move(
    direction: MovementDirection,
    goal_id: UUID,
    payload: MoveRequest,
    user: AuthenticatedUser,
    idem: tuple[str, str],
    session: AsyncSession,
) -> MovementResponse:
    """Same order as a transfer: authorize -> validate -> idempotency ->
    move. Whether a goal can cover a withdrawal is decided after the
    key, with the movement (app/services/savings.py): checked before
    it, the replay of the very request that emptied the goal would be
    refused."""
    goal = await _open_goal(session, goal_id, user.user_id)
    wallet = await ledger.ledger_client.get_wallet(
        payload.wallet_id, user_bearer_token=user.access_token
    )
    if wallet is None:
        raise WalletNotFoundError(str(payload.wallet_id))
    if wallet.currency != goal.currency:
        raise CurrencyMismatchError(
            f"the goal is in {goal.currency}; this wallet is {wallet.currency}"
        )
    amount_minor = parse_positive_amount(payload.amount, goal.currency)
    pool = await ledger.ledger_client.get_system_account("SAVINGS", goal.currency)
    if pool is None:
        raise SavingsUnavailableError("Savings can't be reached right now. Try again shortly.")

    key, fingerprint = idem
    idempotency_key = await begin_idempotent_request(
        session, user_id=user.user_id, key=key, fingerprint=fingerprint
    )
    movement = await savings.start(
        session,
        savings.MoveInput(
            goal=goal,
            wallet_id=wallet.id,
            pool_account_id=pool,
            direction=direction,
            amount_minor=amount_minor,
            idempotency_key_id=idempotency_key.id,
        ),
    )
    response = MovementResponse.model_validate(movement)
    await complete_idempotent_request(
        session,
        idempotency_key,
        status_code=status.HTTP_201_CREATED,
        body=jsonable_encoder(response),
        resource_id=movement.id,
    )
    return response


@router.post(
    "/{goal_id}/deposit", response_model=MovementResponse, status_code=status.HTTP_201_CREATED
)
async def put_money_in(
    goal_id: UUID,
    payload: MoveRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    idem: tuple[str, str] = Depends(get_idempotency_fingerprint),
    session: AsyncSession = Depends(get_db),
) -> MovementResponse:
    """Moves money from one of the caller's wallets into the goal. Needs
    an Idempotency-Key like any money movement."""
    return await _move(MovementDirection.DEPOSIT, goal_id, payload, user, idem, session)


@router.post(
    "/{goal_id}/withdraw", response_model=MovementResponse, status_code=status.HTTP_201_CREATED
)
async def take_money_out(
    goal_id: UUID,
    payload: MoveRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    idem: tuple[str, str] = Depends(get_idempotency_fingerprint),
    session: AsyncSession = Depends(get_db),
) -> MovementResponse:
    """Moves money from the goal back to one of the caller's wallets.
    More than the goal holds is a FAILED movement (`Insufficient
    Savings`), like a transfer the ledger refuses."""
    return await _move(MovementDirection.WITHDRAW, goal_id, payload, user, idem, session)


@router.get("/{goal_id}/movements", response_model=list[MovementResponse])
async def list_movements(
    goal_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> list[MovementResponse]:
    """What went into and out of the goal, newest first."""
    await _open_goal(session, goal_id, user.user_id)
    result = await session.execute(
        select(SavingsMovement)
        .where(SavingsMovement.goal_id == goal_id)
        .order_by(SavingsMovement.created_at.desc(), SavingsMovement.id)
        .limit(limit)
        .offset(offset)
    )
    return [MovementResponse.model_validate(item) for item in result.scalars().all()]
