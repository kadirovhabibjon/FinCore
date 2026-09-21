from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.webhook_attempt import WebhookAttempt


class WebhookAttemptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_delivery(self, delivery_id: UUID) -> list[WebhookAttempt]:
        result = await self._session.execute(
            select(WebhookAttempt)
            .where(WebhookAttempt.delivery_id == delivery_id)
            .order_by(WebhookAttempt.attempt_number)
        )
        return list(result.scalars().all())

    async def list_for_deliveries(self, delivery_ids: list[UUID]) -> list[WebhookAttempt]:
        """Batched form of `list_for_delivery`, used when rendering a
        page of deliveries (app/api/v1/webhooks.py) so listing N
        deliveries doesn't cost N+1 queries.
        """
        if not delivery_ids:
            return []
        result = await self._session.execute(
            select(WebhookAttempt)
            .where(WebhookAttempt.delivery_id.in_(delivery_ids))
            .order_by(WebhookAttempt.attempt_number)
        )
        return list(result.scalars().all())
