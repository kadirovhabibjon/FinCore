import logging
from dataclasses import dataclass
from uuid import UUID

import httpx

from app.core.config import settings
from app.domain.transfer import FraudDecision

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FraudCheckResult:
    decision: FraudDecision
    # True when this result came from the failure policy (fraud-service
    # unreachable / erroring), not a real risk assessment — carried
    # through so the caller can flag it (spec Section 12: "ALLOW with
    # flag fraud_unavailable").
    fail_open: bool = False


class FraudClient:
    """Calls fraud-service's synchronous risk check (spec Section 12,
    ADR-0003).

    `httpx.RequestError` (connection refused, DNS failure, timeout) and a
    5xx response are both treated as "fraud-service unavailable" and go
    through the failure policy. A 4xx response is treated as a real bug
    in *this* service's request and is allowed to raise — silently
    routing our own malformed requests through the failure policy would
    hide that kind of bug instead of surfacing it.
    """

    def __init__(
        self,
        base_url: str,
        internal_token: str,
        timeout_seconds: float,
        fail_open_limit_minor: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url
        self._internal_token = internal_token
        self._timeout_seconds = timeout_seconds
        self._fail_open_limit_minor = fail_open_limit_minor
        self._transport = transport

    async def check(
        self,
        *,
        user_id: UUID,
        amount_minor: int,
        currency: str,
        operation_type: str,
        operation_id: UUID,
    ) -> FraudCheckResult:
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    "/internal/v1/risk-checks",
                    json={
                        "user_id": str(user_id),
                        "amount_minor": amount_minor,
                        "currency": currency,
                        "operation_type": operation_type,
                        "operation_id": str(operation_id),
                    },
                    headers={"X-Internal-Token": self._internal_token},
                )
        except httpx.RequestError as exc:
            logger.warning("fraud-service unreachable (%s); applying failure policy", exc)
            return self._apply_failure_policy(amount_minor)

        if response.status_code >= 500:
            logger.warning(
                "fraud-service returned %s; applying failure policy", response.status_code
            )
            return self._apply_failure_policy(amount_minor)

        response.raise_for_status()
        decision = FraudDecision(response.json()["decision"])
        return FraudCheckResult(decision=decision)

    def _apply_failure_policy(self, amount_minor: int) -> FraudCheckResult:
        if amount_minor <= self._fail_open_limit_minor:
            return FraudCheckResult(decision=FraudDecision.ALLOW, fail_open=True)
        return FraudCheckResult(decision=FraudDecision.REVIEW, fail_open=True)


fraud_client = FraudClient(
    base_url=settings.fraud_service_base_url,
    internal_token=settings.internal_service_token,
    timeout_seconds=settings.fraud_service_timeout_seconds,
    fail_open_limit_minor=settings.fraud_fail_open_limit_minor,
)
