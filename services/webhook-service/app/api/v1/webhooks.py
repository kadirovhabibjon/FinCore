from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import AuthenticatedUser, get_authenticated_user
from app.api.v1.schemas import (
    CreateWebhookEndpointRequest,
    WebhookAttemptResponse,
    WebhookDeliveryResponse,
    WebhookEndpointResponse,
    WebhookEndpointWithSecretResponse,
)
from app.core.exceptions import WebhookEndpointNotFoundError
from app.db.session import get_db
from app.domain.webhook_endpoint import WebhookEndpoint
from app.repositories.webhook_attempt_repository import WebhookAttemptRepository
from app.repositories.webhook_delivery_repository import WebhookDeliveryRepository
from app.repositories.webhook_endpoint_repository import WebhookEndpointRepository
from app.services import endpoints as endpoints_service
from app.services import merchants as merchants_module

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


async def _get_owned_endpoint(
    endpoint_id: UUID, owner_user_id: UUID, session: AsyncSession
) -> WebhookEndpoint:
    endpoint = await WebhookEndpointRepository(session).get(endpoint_id)
    # Same anti-enumeration reasoning as MerchantNotFoundError: "doesn't
    # exist" and "exists but isn't yours" get the same response.
    if endpoint is None or endpoint.owner_user_id != owner_user_id:
        raise WebhookEndpointNotFoundError(str(endpoint_id))
    return endpoint


@router.post(
    "/endpoints",
    response_model=WebhookEndpointWithSecretResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_endpoint(
    payload: CreateWebhookEndpointRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> WebhookEndpointWithSecretResponse:
    endpoint = await endpoints_service.register_endpoint(
        session,
        merchants_module.merchant_client,
        owner_user_id=user.user_id,
        merchant_id=payload.merchant_id,
        url=payload.url,
    )
    return WebhookEndpointWithSecretResponse.model_validate(endpoint)


@router.get("/endpoints", response_model=list[WebhookEndpointResponse])
async def list_my_endpoints(
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> list[WebhookEndpointResponse]:
    rows = await WebhookEndpointRepository(session).list_for_owner(user.user_id)
    return [WebhookEndpointResponse.model_validate(row) for row in rows]


@router.get("/endpoints/{endpoint_id}", response_model=WebhookEndpointResponse)
async def get_endpoint(
    endpoint_id: UUID,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> WebhookEndpointResponse:
    endpoint = await _get_owned_endpoint(endpoint_id, user.user_id, session)
    return WebhookEndpointResponse.model_validate(endpoint)


@router.post(
    "/endpoints/{endpoint_id}/rotate-secret", response_model=WebhookEndpointWithSecretResponse
)
async def rotate_secret(
    endpoint_id: UUID,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> WebhookEndpointWithSecretResponse:
    endpoint = await _get_owned_endpoint(endpoint_id, user.user_id, session)
    endpoint = await endpoints_service.rotate_secret(session, endpoint)
    return WebhookEndpointWithSecretResponse.model_validate(endpoint)


@router.post("/endpoints/{endpoint_id}/enable", response_model=WebhookEndpointResponse)
async def enable_endpoint(
    endpoint_id: UUID,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> WebhookEndpointResponse:
    endpoint = await _get_owned_endpoint(endpoint_id, user.user_id, session)
    endpoint = await endpoints_service.enable_endpoint(session, endpoint)
    return WebhookEndpointResponse.model_validate(endpoint)


@router.get("/endpoints/{endpoint_id}/deliveries", response_model=list[WebhookDeliveryResponse])
async def list_deliveries(
    endpoint_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> list[WebhookDeliveryResponse]:
    """Delivery history (spec Section 17: "every attempt with status
    code and latency") — each delivery's own attempts embedded, so a
    merchant can see the full retry sequence for one event without a
    second call per delivery.
    """
    await _get_owned_endpoint(endpoint_id, user.user_id, session)
    return await load_delivery_history(session, endpoint_id, limit=limit, offset=offset)


async def load_delivery_history(
    session: AsyncSession, endpoint_id: UUID, *, limit: int, offset: int
) -> list[WebhookDeliveryResponse]:
    """Shared with the admin API (app/api/v1/admin.py), which shows the
    same history for any endpoint rather than only the caller's own.
    """
    delivery_repository = WebhookDeliveryRepository(session)
    deliveries = await delivery_repository.list_for_endpoint(
        endpoint_id, limit=limit, offset=offset
    )

    attempts = await WebhookAttemptRepository(session).list_for_deliveries(
        [delivery.id for delivery in deliveries]
    )
    attempts_by_delivery: dict[UUID, list] = {}
    for attempt in attempts:
        attempts_by_delivery.setdefault(attempt.delivery_id, []).append(attempt)

    return [
        WebhookDeliveryResponse(
            id=delivery.id,
            event_id=delivery.event_id,
            event_type=delivery.event_type,
            status=delivery.status.value,
            attempts=delivery.attempts,
            last_error=delivery.last_error,
            created_at=delivery.created_at,
            attempt_history=[
                WebhookAttemptResponse.model_validate(attempt)
                for attempt in attempts_by_delivery.get(delivery.id, [])
            ],
        )
        for delivery in deliveries
    ]
