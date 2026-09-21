from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.refund import Refund, RefundStatus


class RefundRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, refund_id: UUID) -> Refund | None:
        return await self._session.get(Refund, refund_id)

    async def list_for_payment(self, payment_id: UUID) -> list[Refund]:
        result = await self._session.execute(
            select(Refund).where(Refund.payment_id == payment_id).order_by(Refund.created_at)
        )
        return list(result.scalars().all())

    async def list_stuck_pending(self, *, older_than: datetime) -> list[Refund]:
        """PENDING refunds whose posting outcome was never confirmed
        (spec Section 10.1's "unknown outcome" reasoning, applied here
        too). Used by the recovery worker.
        """
        result = await self._session.execute(
            select(Refund)
            .where(Refund.status == RefundStatus.PENDING, Refund.updated_at < older_than)
            .order_by(Refund.updated_at)
        )
        return list(result.scalars().all())

    async def transition_status(
        self,
        refund_id: UUID,
        *,
        expected: RefundStatus,
        new_status: RefundStatus,
        **extra_fields: Any,
    ) -> bool:
        result = await self._session.execute(
            update(Refund)
            .where(Refund.id == refund_id, Refund.status == expected)
            .values(status=new_status, **extra_fields)
        )
        return result.rowcount == 1  # type: ignore[attr-defined]
