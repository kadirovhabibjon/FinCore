import uuid

import pytest
from fincore_common import EventEnvelope, EventType
from sqlalchemy import select

from app.db import session as db_session
from app.domain.audit_log import AuditLog
from app.services.consumer import persist_audit_log

pytestmark = pytest.mark.usefixtures("migrated_database")


def _envelope(**overrides: object) -> EventEnvelope:
    data = {
        "transfer_id": str(uuid.uuid4()),
        "reference": "TRF-PERSIST001",
        "initiator_user_id": str(uuid.uuid4()),
        "amount_minor": 500_00,
        "currency": "UZS",
        "status": "COMPLETED",
        "failure_reason": None,
        "completed_at": "2026-01-01T00:00:00Z",
    }
    data.update(overrides)
    return EventEnvelope(
        event_type=EventType.TRANSFER_COMPLETED,
        producer="payment-service",
        correlation_id="corr-persist-1",
        data=data,
    )


async def _rows_for(event_id: uuid.UUID) -> list[AuditLog]:
    async with db_session.async_session_factory() as session:
        result = await session.execute(select(AuditLog).where(AuditLog.event_id == event_id))
        return list(result.scalars().all())


async def test_persisting_an_event_writes_one_audit_row() -> None:
    envelope = _envelope()

    await persist_audit_log(envelope)

    rows = await _rows_for(envelope.event_id)
    assert len(rows) == 1
    assert rows[0].action == "TRANSFER_COMPLETED"
    assert rows[0].resource_id == envelope.data["transfer_id"]


async def test_persisting_the_same_event_id_twice_only_writes_once() -> None:
    """spec Section 14.3's "consumer idempotency," applied to the audit
    trail itself: a redelivered event must not appear twice.
    """
    envelope = _envelope()

    await persist_audit_log(envelope)
    await persist_audit_log(envelope)

    rows = await _rows_for(envelope.event_id)
    assert len(rows) == 1
