from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.webhook_endpoint import WebhookEndpoint, WebhookEndpointStatus


class WebhookEndpointRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, endpoint_id: UUID) -> WebhookEndpoint | None:
        return await self._session.get(WebhookEndpoint, endpoint_id)

    async def list_for_owner(self, owner_user_id: UUID) -> list[WebhookEndpoint]:
        result = await self._session.execute(
            select(WebhookEndpoint)
            .where(WebhookEndpoint.owner_user_id == owner_user_id)
            .order_by(WebhookEndpoint.created_at)
        )
        return list(result.scalars().all())

    async def list_all(
        self,
        *,
        status: WebhookEndpointStatus | None,
        merchant_id: UUID | None,
        limit: int,
        offset: int,
    ) -> list[WebhookEndpoint]:
        """Every owner's endpoints, newest first — the admin view."""
        query = select(WebhookEndpoint)
        if status is not None:
            query = query.where(WebhookEndpoint.status == status)
        if merchant_id is not None:
            query = query.where(WebhookEndpoint.merchant_id == merchant_id)
        result = await self._session.execute(
            query.order_by(WebhookEndpoint.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def list_active_for_merchant(self, merchant_id: UUID) -> list[WebhookEndpoint]:
        """Used by the Kafka consumer (app/services/consumer.py) to fan
        an incoming event out to every endpoint currently eligible to
        receive it. A DISABLED endpoint is excluded here rather than
        filtered at delivery time, so no delivery row is ever created
        for it in the first place.
        """
        result = await self._session.execute(
            select(WebhookEndpoint).where(
                WebhookEndpoint.merchant_id == merchant_id,
                WebhookEndpoint.status == WebhookEndpointStatus.ACTIVE,
            )
        )
        return list(result.scalars().all())

    async def record_delivery_success(self, endpoint_id: UUID) -> None:
        """Called once a delivery to this endpoint actually succeeds —
        clears whatever run of terminal failures preceded it, since the
        endpoint has just proven it's reachable again.
        """
        await self._session.execute(
            update(WebhookEndpoint)
            .where(WebhookEndpoint.id == endpoint_id)
            .values(consecutive_failures=0)
        )

    async def record_delivery_failure(self, endpoint_id: UUID, *, disable_after: int) -> None:
        """Called once a *delivery* (not a single attempt) is terminally
        FAILED — i.e. it exhausted every retry, not merely failed once
        within its own backoff sequence. Auto-disables the endpoint
        (spec Section 17) once this run reaches `disable_after`.
        """
        result = await self._session.execute(
            update(WebhookEndpoint)
            .where(WebhookEndpoint.id == endpoint_id)
            .values(consecutive_failures=WebhookEndpoint.consecutive_failures + 1)
            .returning(WebhookEndpoint.consecutive_failures)
        )
        new_count = result.scalar_one()
        if new_count >= disable_after:
            await self._session.execute(
                update(WebhookEndpoint)
                .where(
                    WebhookEndpoint.id == endpoint_id,
                    WebhookEndpoint.status == WebhookEndpointStatus.ACTIVE,
                )
                .values(status=WebhookEndpointStatus.DISABLED)
            )
