from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.internal.schemas import (
    CaptureHoldRequest,
    CreateHoldRequest,
    HoldResponse,
    PostingResponse,
)
from app.core.auth import require_internal_service
from app.db.session import get_db
from app.services.holds import capture_hold, create_hold, release_hold

router = APIRouter(
    prefix="/internal/v1/holds",
    tags=["internal"],
    dependencies=[Depends(require_internal_service)],
)


@router.post("", response_model=HoldResponse, status_code=status.HTTP_201_CREATED)
async def post_hold(
    payload: CreateHoldRequest,
    session: AsyncSession = Depends(get_db),
) -> HoldResponse:
    hold = await create_hold(
        session,
        source_service=payload.source_service,
        source_id=payload.source_id,
        account_id=payload.account_id,
        amount_minor=payload.amount_minor,
        currency=payload.currency,
        ttl_seconds=payload.ttl_seconds,
    )
    return HoldResponse.model_validate(hold)


@router.post("/{hold_id}/capture", response_model=PostingResponse)
async def post_capture(
    hold_id: UUID,
    payload: CaptureHoldRequest,
    session: AsyncSession = Depends(get_db),
) -> PostingResponse:
    posting = await capture_hold(
        session,
        hold_id,
        amount_minor=payload.amount_minor,
        source_service=payload.source_service,
        source_id=payload.source_id,
    )
    return PostingResponse.model_validate(posting)


@router.post("/{hold_id}/release", response_model=HoldResponse)
async def post_release(
    hold_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> HoldResponse:
    hold = await release_hold(session, hold_id)
    return HoldResponse.model_validate(hold)
