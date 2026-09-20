import uuid

import pytest

from app.core.config import settings
from app.db import session as db_session
from app.domain.fraud_check import FraudCheck, FraudDecision
from app.services.risk_check import perform_risk_check
from app.services.rules import (
    HighFrequencyRule,
    LargeAmountRule,
    RepeatedFailuresRule,
    RiskContext,
    RiskEngine,
)

pytestmark = pytest.mark.usefixtures("migrated_database")


async def _seed_check(
    *,
    user_id: uuid.UUID,
    amount_minor: int = 100_00,
    decision: FraudDecision = FraudDecision.ALLOW,
) -> None:
    async with db_session.async_session_factory() as session:
        session.add(
            FraudCheck(
                operation_id=uuid.uuid4(),
                operation_type="TRANSFER",
                user_id=user_id,
                amount_minor=amount_minor,
                currency="UZS",
                score=0,
                decision=decision,
                rules_triggered=[],
            )
        )
        await session.commit()


def _context(user_id: uuid.UUID, amount_minor: int = 100_00) -> RiskContext:
    return RiskContext(
        user_id=user_id,
        amount_minor=amount_minor,
        currency="UZS",
        operation_type="TRANSFER",
        operation_id=uuid.uuid4(),
    )


async def test_large_amount_rule_triggers_above_the_threshold() -> None:
    rule = LargeAmountRule()
    over = settings.large_amount_threshold_minor + 1
    under = settings.large_amount_threshold_minor

    async with db_session.async_session_factory() as session:
        assert await rule.evaluate(session, _context(uuid.uuid4(), amount_minor=over)) is True
        assert await rule.evaluate(session, _context(uuid.uuid4(), amount_minor=under)) is False


async def test_high_frequency_rule_triggers_once_the_window_is_full() -> None:
    user_id = uuid.uuid4()
    rule = HighFrequencyRule()

    async with db_session.async_session_factory() as session:
        assert await rule.evaluate(session, _context(user_id)) is False

    for _ in range(settings.high_frequency_max_checks):
        await _seed_check(user_id=user_id)

    async with db_session.async_session_factory() as session:
        assert await rule.evaluate(session, _context(user_id)) is True


async def test_high_frequency_rule_does_not_count_other_users() -> None:
    user_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    for _ in range(settings.high_frequency_max_checks):
        await _seed_check(user_id=other_user_id)

    rule = HighFrequencyRule()
    async with db_session.async_session_factory() as session:
        assert await rule.evaluate(session, _context(user_id)) is False


async def test_repeated_failures_rule_triggers_on_prior_review_or_block_decisions() -> None:
    user_id = uuid.uuid4()
    rule = RepeatedFailuresRule()

    async with db_session.async_session_factory() as session:
        assert await rule.evaluate(session, _context(user_id)) is False

    for _ in range(settings.repeated_failures_max_count):
        await _seed_check(user_id=user_id, decision=FraudDecision.BLOCK)

    async with db_session.async_session_factory() as session:
        assert await rule.evaluate(session, _context(user_id)) is True


async def test_repeated_failures_rule_ignores_prior_allow_decisions() -> None:
    user_id = uuid.uuid4()
    for _ in range(settings.repeated_failures_max_count + 5):
        await _seed_check(user_id=user_id, decision=FraudDecision.ALLOW)

    rule = RepeatedFailuresRule()
    async with db_session.async_session_factory() as session:
        assert await rule.evaluate(session, _context(user_id)) is False


async def test_engine_combines_triggered_rules_into_one_score() -> None:
    user_id = uuid.uuid4()
    for _ in range(settings.repeated_failures_max_count):
        await _seed_check(user_id=user_id, decision=FraudDecision.BLOCK)

    engine = RiskEngine()
    async with db_session.async_session_factory() as session:
        result = await engine.score(
            session,
            _context(user_id, amount_minor=settings.large_amount_threshold_minor + 1),
        )

    assert set(result.rules_triggered) == {"LARGE_AMOUNT", "REPEATED_FAILURES"}
    assert result.score == LargeAmountRule.weight + RepeatedFailuresRule.weight
    assert result.decision == FraudDecision.REVIEW


async def test_perform_risk_check_persists_a_row_matching_the_engine_result() -> None:
    user_id = uuid.uuid4()
    operation_id = uuid.uuid4()
    engine = RiskEngine()

    async with db_session.async_session_factory() as session:
        check = await perform_risk_check(
            session,
            engine,
            operation_id=operation_id,
            operation_type="TRANSFER",
            user_id=user_id,
            amount_minor=100_00,
            currency="UZS",
        )

    assert check.decision == FraudDecision.ALLOW
    assert check.rules_triggered == []
    assert check.operation_id == operation_id
