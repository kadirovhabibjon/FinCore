import enum
from dataclasses import dataclass
from uuid import UUID

import httpx
from fincore_common import async_client

from app.core.config import settings


class MerchantLookupOutcome(enum.Enum):
    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"


@dataclass(frozen=True)
class MerchantInfo:
    id: UUID
    owner_user_id: UUID
    status: str


@dataclass(frozen=True)
class MerchantLookupResult:
    outcome: MerchantLookupOutcome
    merchant: MerchantInfo | None = None


class MerchantClient:
    """Calls payment-service's internal merchant-ownership lookup (spec
    Section 19) when a webhook endpoint is registered — webhook-service
    has no merchants table of its own (database-per-service), so this is
    the only way to know who owns a merchant and whether it's active.

    Unlike FraudClient, there is no fail-open policy here: registering a
    webhook endpoint is not on any money-movement critical path, so if
    payment-service can't be reached the honest answer is "try again",
    not a guess.
    """

    def __init__(
        self,
        base_url: str,
        internal_token: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url
        self._internal_token = internal_token
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def get_merchant(self, merchant_id: UUID) -> MerchantLookupResult:
        async with async_client(
            base_url=self._base_url, timeout=self._timeout_seconds, transport=self._transport
        ) as client:
            response = await client.get(
                f"/internal/v1/merchants/{merchant_id}",
                headers={"X-Internal-Token": self._internal_token},
            )

        if response.status_code == 404:
            return MerchantLookupResult(outcome=MerchantLookupOutcome.NOT_FOUND)

        response.raise_for_status()
        body = response.json()
        return MerchantLookupResult(
            outcome=MerchantLookupOutcome.FOUND,
            merchant=MerchantInfo(
                id=UUID(body["id"]),
                owner_user_id=UUID(body["owner_user_id"]),
                status=body["status"],
            ),
        )


merchant_client = MerchantClient(
    base_url=settings.payment_service_base_url,
    internal_token=settings.internal_service_token,
    timeout_seconds=settings.payment_service_timeout_seconds,
)
