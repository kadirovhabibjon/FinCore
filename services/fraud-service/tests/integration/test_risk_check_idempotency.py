import asyncio
import uuid

import pytest
from sqlalchemy import func, select

from app.db import session as db_session
from app.domain.fraud_check import FraudCheck
from app.services.risk_check import perform_risk_check
from app.services.rules import RiskEngine

pytestmark = pytest.mark.usefixtures("migrated_database")


async def test_repeating_the_same_operation_returns_the_stored_result_without_rescoring() -> None:
    """A retried risk check for the same operation must not count as a
    second operation in its own frequency-based rules' history lookups
    — otherwise retries would inflate a user's own risk score.
    """
    user_id = uuid.uuid4()
    operation_id = uuid.uuid4()
    engine = RiskEngine()

    async with db_session.async_session_factory() as session:
        first = await perform_risk_check(
            session,
            engine,
            operation_id=operation_id,
            operation_type="TRANSFER",
            user_id=user_id,
            amount_minor=100_00,
            currency="UZS",
        )

    async with db_session.async_session_factory() as session:
        second = await perform_risk_check(
            session,
            engine,
            operation_id=operation_id,
            operation_type="TRANSFER",
            user_id=user_id,
            amount_minor=100_00,
            currency="UZS",
        )

    assert first.id == second.id

    async with db_session.async_session_factory() as session:
        result = await session.execute(select(func.count()).select_from(FraudCheck))
        assert result.scalar_one() == 1


async def test_two_concurrent_first_time_checks_for_the_same_operation_produce_one_row() -> None:
    """The UNIQUE(operation_id, operation_type) constraint, not the
    pre-check, is what actually decides this race (this project's
    established "let the database decide" pattern) — verified with a
    real asyncio.gather race against Postgres, not just reasoned about.
    """
    user_id = uuid.uuid4()
    operation_id = uuid.uuid4()
    engine = RiskEngine()

    async def _check() -> uuid.UUID:
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
            return check.id

    first_id, second_id = await asyncio.gather(_check(), _check())

    assert first_id == second_id

    async with db_session.async_session_factory() as session:
        result = await session.execute(select(func.count()).select_from(FraudCheck))
        assert result.scalar_one() == 1
