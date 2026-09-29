import secrets
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import MerchantNotActiveError, MerchantNotFoundError
from app.domain.webhook_endpoint import WebhookEndpoint, WebhookEndpointStatus
from app.services.merchants import MerchantClient, MerchantLookupOutcome
from app.services.ssrf import assert_safe_url


def _generate_secret() -> str:
    # Same construction as identity-service's refresh tokens
    # (app/core/security.py) — 32 random bytes, URL-safe encoded.
    return secrets.token_urlsafe(32)


async def register_endpoint(
    session: AsyncSession,
    merchant_client: MerchantClient,
    *,
    owner_user_id: UUID,
    merchant_id: UUID,
    url: str,
) -> WebhookEndpoint:
    """Registers a webhook endpoint for a merchant (spec Section 17).
    Ownership is verified against payment-service, not trusted from the
    caller's request body — otherwise any authenticated user could
    register a callback for someone else's merchant and start receiving
    their payment events.
    """
    result = await merchant_client.get_merchant(merchant_id)
    if result.outcome is MerchantLookupOutcome.NOT_FOUND or (
        result.merchant is not None and result.merchant.owner_user_id != owner_user_id
    ):
        # Same anti-enumeration reasoning used throughout this project:
        # "doesn't exist" and "exists but isn't yours" get the same
        # response.
        raise MerchantNotFoundError(str(merchant_id))

    assert result.merchant is not None
    if result.merchant.status != "ACTIVE":
        raise MerchantNotActiveError(str(merchant_id))

    await assert_safe_url(url)

    endpoint = WebhookEndpoint(
        merchant_id=merchant_id,
        owner_user_id=owner_user_id,
        url=url,
        secret=_generate_secret(),
    )
    session.add(endpoint)
    await session.commit()
    await session.refresh(endpoint)
    return endpoint


async def rotate_secret(session: AsyncSession, endpoint: WebhookEndpoint) -> WebhookEndpoint:
    """spec Section 17: "per-endpoint secrets ... rotatable." The old
    secret stops working immediately — there is no overlap window, the
    same tradeoff identity-service's own token rotation makes.
    """
    endpoint.secret = _generate_secret()
    await session.commit()
    await session.refresh(endpoint)
    return endpoint


async def disable_endpoint(session: AsyncSession, endpoint: WebhookEndpoint) -> WebhookEndpoint:
    """Staff kill switch (the admin panel, ADR-0005): stops deliveries
    to an endpoint that is misbehaving or abusive without deleting it,
    so its history stays inspectable. Uses the same DISABLED state the
    delivery worker's auto-disable does, so the owner's usual re-enable
    call brings it back once the problem is fixed.
    """
    endpoint.status = WebhookEndpointStatus.DISABLED
    await session.commit()
    await session.refresh(endpoint)
    return endpoint


async def enable_endpoint(session: AsyncSession, endpoint: WebhookEndpoint) -> WebhookEndpoint:
    """Reverses the delivery worker's auto-disable (spec Section 17) —
    the merchant has presumably fixed whatever was rejecting deliveries.
    Resets the failure count too, so it takes a fresh run of failures to
    disable it again rather than one more on top of the old count.
    """
    endpoint.status = WebhookEndpointStatus.ACTIVE
    endpoint.consecutive_failures = 0
    await session.commit()
    await session.refresh(endpoint)
    return endpoint
