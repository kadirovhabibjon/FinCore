from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import AuthenticatedUser, require_roles
from app.api.v1.schemas import AdminWebhookEndpointResponse, WebhookDeliveryResponse
from app.api.v1.webhooks import load_delivery_history
from app.core.exceptions import WebhookEndpointNotFoundError
from app.db.session import get_db
from app.domain.webhook_endpoint import WebhookEndpoint, WebhookEndpointStatus
from app.repositories.webhook_endpoint_repository import WebhookEndpointRepository
from app.services import endpoints as endpoints_service

# ADR-0005's admin panel, same split as identity- and payment-service:
# SUPPORT and ADMIN can look, only ADMIN can change an endpoint's state.
router = APIRouter(prefix="/api/v1/admin/webhooks", tags=["admin"])

_staff = require_roles("SUPPORT", "ADMIN")
_admin = require_roles("ADMIN")


async def _get_endpoint(endpoint_id: UUID, session: AsyncSession) -> WebhookEndpoint:
    endpoint = await WebhookEndpointRepository(session).get(endpoint_id)
    if endpoint is None:
        raise WebhookEndpointNotFoundError(str(endpoint_id))
    return endpoint


@router.get("/endpoints", response_model=list[AdminWebhookEndpointResponse])
async def list_endpoints(
    status: WebhookEndpointStatus | None = Query(default=None),
    merchant_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthenticatedUser = Depends(_staff),
    session: AsyncSession = Depends(get_db),
) -> list[AdminWebhookEndpointResponse]:
    rows = await WebhookEndpointRepository(session).list_all(
        status=status, merchant_id=merchant_id, limit=limit, offset=offset
    )
    return [AdminWebhookEndpointResponse.model_validate(row) for row in rows]


@router.get(
    "/endpoints/{endpoint_id}/deliveries", response_model=list[WebhookDeliveryResponse]
)
async def list_endpoint_deliveries(
    endpoint_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthenticatedUser = Depends(_staff),
    session: AsyncSession = Depends(get_db),
) -> list[WebhookDeliveryResponse]:
    await _get_endpoint(endpoint_id, session)
    return await load_delivery_history(session, endpoint_id, limit=limit, offset=offset)


@router.post("/endpoints/{endpoint_id}/disable", response_model=AdminWebhookEndpointResponse)
async def disable_endpoint(
    endpoint_id: UUID,
    _: AuthenticatedUser = Depends(_admin),
    session: AsyncSession = Depends(get_db),
) -> AdminWebhookEndpointResponse:
    endpoint = await _get_endpoint(endpoint_id, session)
    endpoint = await endpoints_service.disable_endpoint(session, endpoint)
    return AdminWebhookEndpointResponse.model_validate(endpoint)


@router.post("/endpoints/{endpoint_id}/enable", response_model=AdminWebhookEndpointResponse)
async def enable_endpoint(
    endpoint_id: UUID,
    _: AuthenticatedUser = Depends(_admin),
    session: AsyncSession = Depends(get_db),
) -> AdminWebhookEndpointResponse:
    endpoint = await _get_endpoint(endpoint_id, session)
    endpoint = await endpoints_service.enable_endpoint(session, endpoint)
    return AdminWebhookEndpointResponse.model_validate(endpoint)
