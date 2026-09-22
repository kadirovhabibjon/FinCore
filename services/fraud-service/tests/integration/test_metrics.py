import uuid

import pytest

from app.core.metrics import FRAUD_CHECKS_TOTAL
from app.db import session as db_session
from app.domain.fraud_check import FraudDecision
from app.services.risk_check import perform_risk_check
from app.services.rules import RiskEngine

pytestmark = pytest.mark.usefixtures("migrated_database")


def _counter_value(decision: str) -> float:
    return FRAUD_CHECKS_TOTAL.labels(decision=decision)._value.get()


async def test_a_fresh_check_increments_the_counter_for_its_decision() -> None:
    before = _counter_value(FraudDecision.ALLOW.value)

    async with db_session.async_session_factory() as session:
        await perform_risk_check(
            session,
            RiskEngine(),
            operation_id=uuid.uuid4(),
            operation_type="TRANSFER",
            user_id=uuid.uuid4(),
            amount_minor=100_00,
            currency="UZS",
        )

    assert _counter_value(FraudDecision.ALLOW.value) == before + 1


async def test_an_idempotent_replay_does_not_double_count() -> None:
    operation_id = uuid.uuid4()
    engine = RiskEngine()

    async with db_session.async_session_factory() as session:
        await perform_risk_check(
            session,
            engine,
            operation_id=operation_id,
            operation_type="TRANSFER",
            user_id=uuid.uuid4(),
            amount_minor=100_00,
            currency="UZS",
        )

    before = _counter_value(FraudDecision.ALLOW.value)

    async with db_session.async_session_factory() as session:
        await perform_risk_check(
            session,
            engine,
            operation_id=operation_id,
            operation_type="TRANSFER",
            user_id=uuid.uuid4(),
            amount_minor=100_00,
            currency="UZS",
        )

    assert _counter_value(FraudDecision.ALLOW.value) == before
