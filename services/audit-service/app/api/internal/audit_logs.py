from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.internal.schemas import AuditLogResponse
from app.core.auth import require_internal_service
from app.db.session import get_db
from app.repositories.audit_log_repository import AuditLogRepository

router = APIRouter(
    prefix="/internal/v1/audit-logs",
    tags=["internal"],
    dependencies=[Depends(require_internal_service)],
)


@router.get("", response_model=list[AuditLogResponse])
async def search_audit_logs(
    actor_id: UUID | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    resource_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> list[AuditLogResponse]:
    """Read-only — there is no update/delete route, and the database
    role behind this connection has had UPDATE/DELETE/TRUNCATE on
    `audit_logs` revoked at the schema level (spec Section 18), so this
    is the only way in or out of the audit trail besides direct SQL as a
    superuser.
    """
    rows = await AuditLogRepository(session).search(
        actor_id=actor_id,
        resource_type=resource_type,
        resource_id=resource_id,
        action=action,
        limit=limit,
        offset=offset,
    )
    return [AuditLogResponse.model_validate(row) for row in rows]
