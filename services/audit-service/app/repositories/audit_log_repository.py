from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.audit_log import AuditLog


class AuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def exists_for_event(self, event_id: UUID) -> bool:
        result = await self._session.execute(
            select(AuditLog.id).where(AuditLog.event_id == event_id)
        )
        return result.scalar_one_or_none() is not None

    async def search(
        self,
        *,
        actor_id: UUID | None,
        resource_type: str | None,
        resource_id: str | None,
        action: str | None,
        limit: int,
        offset: int,
    ) -> list[AuditLog]:
        """Newest first — the natural order for investigation (spec
        Section 18: "enough information for investigation"). Every
        filter is optional and combines with AND; omitting all of them
        just pages through the full trail.
        """
        query = select(AuditLog)
        if actor_id is not None:
            query = query.where(AuditLog.actor_id == actor_id)
        if resource_type is not None:
            query = query.where(AuditLog.resource_type == resource_type)
        if resource_id is not None:
            query = query.where(AuditLog.resource_id == resource_id)
        if action is not None:
            query = query.where(AuditLog.action == action)

        result = await self._session.execute(
            query.order_by(AuditLog.occurred_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all())
