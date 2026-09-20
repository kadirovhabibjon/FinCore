from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domain.fraud_check import FraudCheck, FraudDecision


@dataclass(frozen=True)
class RiskContext:
    user_id: UUID
    amount_minor: int
    currency: str
    operation_type: str
    operation_id: UUID


class Rule(Protocol):
    """A single fraud signal (spec Section 12's Strategy pattern): each
    rule is evaluated independently and contributes its own fixed
    weight to the total score if triggered, 0 if not. Kept behind this
    interface so the rule set can grow, shrink, or eventually be
    replaced/supplemented by an ML model without touching RiskEngine.

    Two of spec Section 12's example rules — "new device" and
    "suspicious IP" — are deliberately not implemented here: nothing in
    FinCore captures a device fingerprint anywhere yet, and
    payment-service's risk-check request doesn't carry the caller's IP.
    Faking those signals from data that doesn't exist would be worse
    than not having them; the interface here is exactly what lets them
    be added later as real rules once that data actually exists,
    without changing anything else in this service.
    """

    name: str
    weight: int

    async def evaluate(self, session: AsyncSession, context: RiskContext) -> bool: ...


class LargeAmountRule:
    """spec: "Very large payment" -> +30."""

    name = "LARGE_AMOUNT"
    weight = 30

    async def evaluate(self, session: AsyncSession, context: RiskContext) -> bool:
        return context.amount_minor > settings.large_amount_threshold_minor


class HighFrequencyRule:
    """spec: "Too many payments in a short period" / "Unusual
    transaction frequency" -> +25. Counts this user's own prior risk
    checks (any decision) in the trailing window — fraud-service has no
    visibility into payment-service's own Transfer table
    (database-per-service), only its own check history.
    """

    name = "HIGH_FREQUENCY"
    weight = 25

    async def evaluate(self, session: AsyncSession, context: RiskContext) -> bool:
        window_start = datetime.now(UTC) - timedelta(
            seconds=settings.high_frequency_window_seconds
        )
        result = await session.execute(
            select(func.count())
            .select_from(FraudCheck)
            .where(FraudCheck.user_id == context.user_id, FraudCheck.created_at >= window_start)
        )
        return result.scalar_one() >= settings.high_frequency_max_checks


class RepeatedFailuresRule:
    """spec: "Repeated failed payments" — a user REVIEWed or BLOCKed
    more than once recently is itself a signal, independent of this
    particular operation's own amount.
    """

    name = "REPEATED_FAILURES"
    weight = 25

    async def evaluate(self, session: AsyncSession, context: RiskContext) -> bool:
        window_start = datetime.now(UTC) - timedelta(
            seconds=settings.repeated_failures_window_seconds
        )
        result = await session.execute(
            select(func.count())
            .select_from(FraudCheck)
            .where(
                FraudCheck.user_id == context.user_id,
                FraudCheck.created_at >= window_start,
                FraudCheck.decision.in_([FraudDecision.REVIEW, FraudDecision.BLOCK]),
            )
        )
        return result.scalar_one() >= settings.repeated_failures_max_count


DEFAULT_RULES: list[Rule] = [LargeAmountRule(), HighFrequencyRule(), RepeatedFailuresRule()]


@dataclass(frozen=True)
class ScoringResult:
    score: int
    decision: FraudDecision
    rules_triggered: list[str]


def decide(score: int) -> FraudDecision:
    """spec Section 12's thresholds, exactly: 0-39 ALLOW, 40-69 REVIEW, 70+ BLOCK."""
    if score >= 70:
        return FraudDecision.BLOCK
    if score >= 40:
        return FraudDecision.REVIEW
    return FraudDecision.ALLOW


class RiskEngine:
    def __init__(self, rules: list[Rule] | None = None) -> None:
        self._rules = rules if rules is not None else DEFAULT_RULES

    async def score(self, session: AsyncSession, context: RiskContext) -> ScoringResult:
        triggered: list[str] = []
        total = 0
        for rule in self._rules:
            if await rule.evaluate(session, context):
                triggered.append(rule.name)
                total += rule.weight
        return ScoringResult(score=total, decision=decide(total), rules_triggered=triggered)
