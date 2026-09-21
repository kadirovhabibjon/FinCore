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


class HoldOutcome(enum.Enum):
    SUCCESS = "SUCCESS"
    BUSINESS_REJECTION = "BUSINESS_REJECTION"
    # Same "never treated as failure" reasoning as PostingOutcome.UNKNOWN
    # — the hold may or may not actually have been placed.
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class HoldResult:
    outcome: HoldOutcome
    hold_id: UUID | None = None
    failure_reason: str | None = None


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

    async def create_hold(
        self,
        *,
        source_service: str,
        source_id: str,
        account_id: UUID,
        amount_minor: int,
        currency: str,
        ttl_seconds: int,
    ) -> HoldResult:
        """Reserves funds on a wallet (spec Section 8.4's reserve step)
        without moving money. Idempotent on `(source_service,
        source_id)` on ledger-service's side, so a retry after an
        UNKNOWN outcome is safe.
        """
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    "/internal/v1/holds",
                    json={
                        "source_service": source_service,
                        "source_id": source_id,
                        "account_id": str(account_id),
                        "amount_minor": amount_minor,
                        "currency": currency,
                        "ttl_seconds": ttl_seconds,
                    },
                    headers={"X-Internal-Token": self._internal_token},
                )
        except httpx.RequestError as exc:
            logger.warning("ledger-service unreachable (%s); hold outcome unknown", exc)
            return HoldResult(outcome=HoldOutcome.UNKNOWN)

        if response.status_code >= 500:
            logger.warning(
                "ledger-service returned %s; hold outcome unknown", response.status_code
            )
            return HoldResult(outcome=HoldOutcome.UNKNOWN)

        if response.status_code in (200, 201):
            data = response.json()
            return HoldResult(outcome=HoldOutcome.SUCCESS, hold_id=UUID(data["id"]))

        if response.status_code in _BUSINESS_REJECTION_STATUS_CODES:
            detail = response.json()
            return HoldResult(
                outcome=HoldOutcome.BUSINESS_REJECTION,
                failure_reason=detail.get("title", "hold rejected"),
            )

        response.raise_for_status()
        raise AssertionError("unreachable")  # raise_for_status always raises for non-2xx here

    async def capture_hold(
        self, hold_id: UUID, *, amount_minor: int, source_service: str, source_id: str
    ) -> PostingResult:
        """Converts an active hold into a real posting (spec Section
        8.4's capture step). Returns a `PostingResult` — capture and
        create_posting produce the same shape of response on
        ledger-service, and this client's callers already know how to
        branch on a `PostingOutcome`.
        """
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    f"/internal/v1/holds/{hold_id}/capture",
                    json={
                        "source_service": source_service,
                        "source_id": source_id,
                        "amount_minor": amount_minor,
                    },
                    headers={"X-Internal-Token": self._internal_token},
                )
        except httpx.RequestError as exc:
            logger.warning("ledger-service unreachable (%s); capture outcome unknown", exc)
            return PostingResult(outcome=PostingOutcome.UNKNOWN)

        if response.status_code >= 500:
            logger.warning(
                "ledger-service returned %s; capture outcome unknown", response.status_code
            )
            return PostingResult(outcome=PostingOutcome.UNKNOWN)

        if response.status_code in (200, 201):
            data = response.json()
            return PostingResult(outcome=PostingOutcome.SUCCESS, posting_id=UUID(data["id"]))

        if response.status_code in _BUSINESS_REJECTION_STATUS_CODES:
            detail = response.json()
            return PostingResult(
                outcome=PostingOutcome.BUSINESS_REJECTION,
                failure_reason=detail.get("title", "capture rejected"),
            )

        response.raise_for_status()
        raise AssertionError("unreachable")  # raise_for_status always raises for non-2xx here

    async def release_hold(self, hold_id: UUID) -> None:
        """Best-effort cleanup after a capture business-rejection — not
        itself a saga outcome any caller needs to branch on, so failures
        here are logged and swallowed rather than raised: the hold will
        expire on its own (spec Section 8.4) even if this call never
        lands.
        """
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    f"/internal/v1/holds/{hold_id}/release",
                    headers={"X-Internal-Token": self._internal_token},
                )
            if response.status_code >= 400:
                logger.warning("releasing hold %s returned %s", hold_id, response.status_code)
        except httpx.RequestError as exc:
            logger.warning("ledger-service unreachable (%s) while releasing hold %s", exc, hold_id)

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

    async def get_system_account(self, kind: str, currency: str) -> UUID | None:
        """Looks up a pooled system account's id (e.g. MERCHANT_SETTLEMENT
        for a currency), for building a refund posting's entries
        directly (spec Section 11: "refunds as new postings"). Unlike
        holds/capture, there's no ledger-service endpoint that already
        knows "refund" as a concept — this is the one piece of
        information payment-service needs to construct that posting
        itself via the generic `create_posting`.
        """
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.get(
                    "/internal/v1/accounts/system",
                    params={"kind": kind, "currency": currency},
                    headers={"X-Internal-Token": self._internal_token},
                )
        except httpx.RequestError as exc:
            logger.warning("ledger-service unreachable (%s) while looking up %s", exc, kind)
            return None

        if response.status_code == 404:
            return None

        response.raise_for_status()
        data = response.json()
        return UUID(data["id"])


ledger_client = LedgerClient(
    base_url=settings.ledger_service_base_url,
    internal_token=settings.internal_service_token,
    timeout_seconds=settings.ledger_service_timeout_seconds,
)
