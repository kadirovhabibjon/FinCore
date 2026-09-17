import enum
import logging
from dataclasses import dataclass
from uuid import UUID

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class PostingOutcome(enum.Enum):
    SUCCESS = "SUCCESS"
    BUSINESS_REJECTION = "BUSINESS_REJECTION"
    # A timeout, connection failure, or 5xx from ledger-service: money may
    # or may not have actually moved. Never treated as failure (spec
    # Section 10.1's revision notes) — the caller must not mark its own
    # operation FAILED on this outcome.
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class PostingResult:
    outcome: PostingOutcome
    posting_id: UUID | None = None
    failure_reason: str | None = None


@dataclass(frozen=True)
class WalletInfo:
    id: UUID
    currency: str
    status: str


# Business-rejection status codes ledger-service's internal postings API
# is documented to return (insufficient funds, account not active,
# currency mismatch, unbalanced posting, unknown account) — anything
# outside this set is treated as a real bug (auth misconfiguration,
# unexpected error) and allowed to raise, not silently folded into
# UNKNOWN or BUSINESS_REJECTION.
_BUSINESS_REJECTION_STATUS_CODES = {404, 409, 422}


class LedgerClient:
    """Talks to ledger-service both as an internal caller (the postings
    API, shared-secret authenticated) and, for wallet-ownership checks,
    as a relay of the end user's own bearer token against ledger-service's
    *public* wallet endpoint — reusing its existing ownership check
    instead of duplicating that logic here or adding a new internal
    endpoint just for this.
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

    async def create_posting(
        self,
        *,
        source_service: str,
        source_id: str,
        type: str,
        currency: str,
        entries: list[dict[str, object]],
    ) -> PostingResult:
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    "/internal/v1/postings",
                    json={
                        "source_service": source_service,
                        "source_id": source_id,
                        "type": type,
                        "currency": currency,
                        "entries": entries,
                    },
                    headers={"X-Internal-Token": self._internal_token},
                )
        except httpx.RequestError as exc:
            logger.warning("ledger-service unreachable (%s); posting outcome unknown", exc)
            return PostingResult(outcome=PostingOutcome.UNKNOWN)

        if response.status_code >= 500:
            logger.warning(
                "ledger-service returned %s; posting outcome unknown", response.status_code
            )
            return PostingResult(outcome=PostingOutcome.UNKNOWN)

        if response.status_code in (200, 201):
            data = response.json()
            return PostingResult(outcome=PostingOutcome.SUCCESS, posting_id=UUID(data["id"]))

        if response.status_code in _BUSINESS_REJECTION_STATUS_CODES:
            detail = response.json()
            return PostingResult(
                outcome=PostingOutcome.BUSINESS_REJECTION,
                failure_reason=detail.get("title", "posting rejected"),
            )

        response.raise_for_status()
        raise AssertionError("unreachable")  # raise_for_status always raises for non-2xx here

    async def get_posting(
        self, *, source_service: str, source_id: str, type: str
    ) -> PostingResult:
        """Used by the recovery worker to resolve a posting whose
        original create call returned UNKNOWN (spec Section 10.1).
        """
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.get(
                    f"/internal/v1/postings/{source_id}",
                    params={"source_service": source_service, "type": type},
                    headers={"X-Internal-Token": self._internal_token},
                )
        except httpx.RequestError as exc:
            logger.warning("ledger-service unreachable (%s); posting still unknown", exc)
            return PostingResult(outcome=PostingOutcome.UNKNOWN)

        if response.status_code == 404:
            return PostingResult(outcome=PostingOutcome.UNKNOWN)
        if response.status_code >= 500:
            return PostingResult(outcome=PostingOutcome.UNKNOWN)

        response.raise_for_status()
        data = response.json()
        return PostingResult(outcome=PostingOutcome.SUCCESS, posting_id=UUID(data["id"]))

    async def get_wallet(self, wallet_id: UUID, *, user_bearer_token: str) -> WalletInfo | None:
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.get(
                    f"/api/v1/wallets/{wallet_id}",
                    headers={"Authorization": f"Bearer {user_bearer_token}"},
                )
        except httpx.RequestError as exc:
            logger.warning("ledger-service unreachable (%s) while checking wallet ownership", exc)
            return None

        if response.status_code == 404:
            return None

        response.raise_for_status()
        data = response.json()
        return WalletInfo(id=UUID(data["id"]), currency=data["currency"], status=data["status"])


ledger_client = LedgerClient(
    base_url=settings.ledger_service_base_url,
    internal_token=settings.internal_service_token,
    timeout_seconds=settings.ledger_service_timeout_seconds,
)
