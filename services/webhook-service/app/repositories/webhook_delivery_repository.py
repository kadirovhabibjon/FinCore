from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.webhook_delivery import WebhookDelivery, WebhookDeliveryStatus


class WebhookDeliveryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, delivery_id: UUID) -> WebhookDelivery | None:
        return await self._session.get(WebhookDelivery, delivery_id)

    async def exists_for_endpoint_and_event(self, endpoint_id: UUID, event_id: UUID) -> bool:
        result = await self._session.execute(
            select(WebhookDelivery.id).where(
                WebhookDelivery.endpoint_id == endpoint_id, WebhookDelivery.event_id == event_id
            )
        )
        return result.scalar_one_or_none() is not None

    async def list_for_endpoint(
        self, endpoint_id: UUID, *, limit: int, offset: int
    ) -> list[WebhookDelivery]:
        result = await self._session.execute(
            select(WebhookDelivery)
            .where(WebhookDelivery.endpoint_id == endpoint_id)
            .order_by(WebhookDelivery.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def list_due(self, *, now: datetime, limit: int) -> list[WebhookDelivery]:
        """Rows the delivery worker should attempt this pass (spec
        Section 17's retry-with-backoff): still PENDING and due, oldest
        due first. A row created just now (next_attempt_at = its own
        created_at) is picked up on the very next tick.
        """
        result = await self._session.execute(
            select(WebhookDelivery)
            .where(
                WebhookDelivery.status == WebhookDeliveryStatus.PENDING,
                WebhookDelivery.next_attempt_at <= now,
            )
            .order_by(WebhookDelivery.next_attempt_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_succeeded(self, delivery_id: UUID, *, attempts: int) -> bool:
        result = await self._session.execute(
            update(WebhookDelivery)
            .where(
                WebhookDelivery.id == delivery_id,
                WebhookDelivery.status == WebhookDeliveryStatus.PENDING,
            )
            .values(status=WebhookDeliveryStatus.SUCCEEDED, attempts=attempts, last_error=None)
        )
        return result.rowcount == 1  # type: ignore[attr-defined]

    async def reschedule(
        self, delivery_id: UUID, *, attempts: int, next_attempt_at: datetime, last_error: str
    ) -> bool:
        """A failed attempt with retries left — pushes `next_attempt_at`
        out by the caller's backoff calculation (app/services/retry.py).
        """
        result = await self._session.execute(
            update(WebhookDelivery)
            .where(
                WebhookDelivery.id == delivery_id,
                WebhookDelivery.status == WebhookDeliveryStatus.PENDING,
            )
            .values(attempts=attempts, next_attempt_at=next_attempt_at, last_error=last_error)
        )
        return result.rowcount == 1  # type: ignore[attr-defined]

    async def mark_failed(self, delivery_id: UUID, *, attempts: int, last_error: str) -> bool:
        """Attempts exhausted (or the endpoint was disabled mid-flight)
        — terminal, not retried further automatically.
        """
        result = await self._session.execute(
            update(WebhookDelivery)
            .where(
                WebhookDelivery.id == delivery_id,
                WebhookDelivery.status == WebhookDeliveryStatus.PENDING,
            )
            .values(status=WebhookDeliveryStatus.FAILED, attempts=attempts, last_error=last_error)
        )
        return result.rowcount == 1  # type: ignore[attr-defined]
