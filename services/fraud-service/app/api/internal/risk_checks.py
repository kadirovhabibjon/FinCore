from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.internal.schemas import RiskCheckRequest, RiskCheckResponse
from app.core.auth import require_internal_service
from app.db.session import get_db
from app.services.risk_check import perform_risk_check
from app.services.rules import RiskEngine

router = APIRouter(
    prefix="/internal/v1/risk-checks",
    tags=["internal"],
    dependencies=[Depends(require_internal_service)],
)

_engine = RiskEngine()


@router.post("", response_model=RiskCheckResponse, status_code=status.HTTP_201_CREATED)
async def post_risk_check(
    payload: RiskCheckRequest,
    session: AsyncSession = Depends(get_db),
) -> RiskCheckResponse:
    check = await perform_risk_check(
        session,
        _engine,
        operation_id=payload.operation_id,
        operation_type=payload.operation_type,
        user_id=payload.user_id,
        amount_minor=payload.amount_minor,
        currency=payload.currency,
    )
    return RiskCheckResponse.model_validate(check)
