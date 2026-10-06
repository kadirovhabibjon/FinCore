from datetime import datetime
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.money_request import MoneyRequest, MoneyRequestStatus

_OPEN = (MoneyRequestStatus.PENDING, MoneyRequestStatus.PAYING)


class MoneyRequestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, request: MoneyRequest) -> None:
        self._session.add(request)

    async def get(self, request_id: UUID) -> MoneyRequest | None:
        return await self._session.get(MoneyRequest, request_id)

    async def list_for_user(self, user_id: UUID, *, limit: int) -> list[MoneyRequest]:
        """Requests the user made or was sent, newest first."""
        result = await self._session.execute(
            select(MoneyRequest)
            .where(
                or_(
                    MoneyRequest.requester_user_id == user_id,
                    MoneyRequest.payer_user_id == user_id,
                )
            )
            .order_by(MoneyRequest.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_open(
        self, requester_user_id: UUID, *, payer_user_id: UUID | None = None
    ) -> int:
        query = (
            select(func.count())
            .select_from(MoneyRequest)
            .where(
                MoneyRequest.requester_user_id == requester_user_id,
                MoneyRequest.status.in_(_OPEN),
            )
        )
        if payer_user_id is not None:
            query = query.where(MoneyRequest.payer_user_id == payer_user_id)
        return int((await self._session.execute(query)).scalar_one())

    async def transition(
        self,
        request_id: UUID,
        *,
        expected: MoneyRequestStatus,
        new_status: MoneyRequestStatus,
        stale_before: datetime | None = None,
        **values: object,
    ) -> bool:
        """Atomic `UPDATE ... WHERE status = :expected`: whether this call
        was the one that made the change. With `stale_before`, it only
        applies to a row not touched since then."""
        query = update(MoneyRequest).where(
            MoneyRequest.id == request_id, MoneyRequest.status == expected
        )
        if stale_before is not None:
            query = query.where(MoneyRequest.updated_at < stale_before)
        result = await self._session.execute(query.values(status=new_status, **values))
        return bool(result.rowcount)  # type: ignore[attr-defined]
