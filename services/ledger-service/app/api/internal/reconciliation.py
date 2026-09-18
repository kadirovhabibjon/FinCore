from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.internal.schemas import ReconciliationReportResponse
from app.core.auth import require_internal_service
from app.db.session import get_db
from app.services.reconciliation import run_reconciliation

router = APIRouter(
    prefix="/internal/v1/reconciliation",
    tags=["internal"],
    dependencies=[Depends(require_internal_service)],
)


@router.get("", response_model=ReconciliationReportResponse)
async def get_reconciliation_report(
    session: AsyncSession = Depends(get_db),
) -> ReconciliationReportResponse:
    """Triggers one reconciliation pass on demand (spec Section 8.4) — for
    ops/debugging between the background loop's own scheduled runs
    (app/main.py). Does not auto-correct anything it finds (ADR-0002).
    """
    report = await run_reconciliation(session)
    return ReconciliationReportResponse(
        is_clean=report.is_clean,
        unbalanced_postings=report.unbalanced_postings,
        balance_mismatches=report.balance_mismatches,
        negative_available_wallets=report.negative_available_wallets,
        duplicate_source_postings=report.duplicate_source_postings,
    )
