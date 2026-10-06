from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exchange import Exchange, ExchangeStatus

# Statuses a saga can still be continued from.
UNFINISHED = (ExchangeStatus.PENDING, ExchangeStatus.DEBITED, ExchangeStatus.REVERSING)


class ExchangeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, exchange_id: UUID) -> Exchange | None:
        return await self._session.get(Exchange, exchange_id)

    async def list_for_user(self, user_id: UUID, *, limit: int, offset: int) -> list[Exchange]:
        result = await self._session.execute(
            select(Exchange)
            .where(Exchange.initiator_user_id == user_id)
            .order_by(Exchange.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def list_stuck(self, *, older_than: datetime) -> list[Exchange]:
        """Exchanges left mid-saga by an unknown ledger outcome, not
        touched since `older_than` (a request still in flight is left
        alone)."""
        result = await self._session.execute(
            select(Exchange)
            .where(Exchange.status.in_(UNFINISHED), Exchange.updated_at < older_than)
            .order_by(Exchange.updated_at)
        )
        return list(result.scalars().all())

    async def transition(
        self,
        exchange_id: UUID,
        *,
        expected: ExchangeStatus,
        new_status: ExchangeStatus,
        **values: object,
    ) -> bool:
        """Atomic `UPDATE ... WHERE status = :expected`: whether this
        call made the change. Two workers continuing the same exchange
        (the request and the recovery pass) cannot both advance it."""
        result = await self._session.execute(
            update(Exchange)
            .where(Exchange.id == exchange_id, Exchange.status == expected)
            .values(status=new_status, **values)
        )
        return bool(result.rowcount)  # type: ignore[attr-defined]
