import logging
from uuid import UUID

from fincore_common import EventEnvelope
from sqlalchemy.exc import IntegrityError

from app.db import session as db_session
from app.domain.audit_log import AuditLog
from app.repositories.audit_log_repository import AuditLogRepository

logger = logging.getLogger(__name__)

# Fields lifted onto their own columns; everything else in the event's
# `data` lands in `details` instead — none of it is a password, token,
# card number or secret key (spec Section 18), since none of this
# service's source events carry any of those in the first place.
_LIFTED_FIELDS = frozenset(
    {
        "transfer_id",
        "payment_id",
        "request_id",
        "user_id",
        "operation_id",
        "initiator_user_id",
        "actor_user_id",
        "status",
        "decision",
        "reference",
    }
)

# Where each topic's events name the aggregate they're about, who acted,
# and the outcome: payment-service's carry the initiating user and a
# status; identity-service's (`users`) name the account and, separately,
# who changed it — an ADMIN, the user themselves, or nobody (the operator
# CLI); fraud-service's (`fraud`) are filed under the transfer or payment
# they were about (operation_id), so one operation's trail reads as a
# whole, with the risk decision as the result. operation_id comes before
# user_id: order matters only if an event ever carries both.
_RESOURCE_ID_FIELDS = ("transfer_id", "payment_id", "request_id", "operation_id", "user_id")
_ACTOR_FIELDS = ("initiator_user_id", "actor_user_id")
_RESULT_FIELDS = ("status", "decision")


class MalformedEventError(Exception):
    """The envelope is missing a field every event on these topics is
    documented to carry (spec Section 14.3) — a producer bug, not
    something retrying will fix. Classified as permanent in
    app/services/retry.py.
    """


def _resource_type(event_type: str) -> str:
    aggregate, _, _ = event_type.partition(".")
    return aggregate.capitalize()


def _resource_id(data: dict) -> str:
    for field in _RESOURCE_ID_FIELDS:
        if data.get(field):
            return str(data[field])
    raise MalformedEventError(f"event data has none of {', '.join(_RESOURCE_ID_FIELDS)}")


def _actor_id(data: dict) -> UUID | None:
    for field in _ACTOR_FIELDS:
        if data.get(field):
            return UUID(data[field])
    return None


def handle_domain_event(envelope: EventEnvelope) -> AuditLog:
    """Builds the audit row for one event — pure, so it's trivially unit
    testable without a database. `app/services/dispatch.py` is what
    actually persists the result and handles idempotency/retry.

    `action` is derived mechanically from `event_type`
    ("transfer.completed" -> "TRANSFER_COMPLETED"), which happens to
    match spec Section 18's own example action names exactly — this
    consumer doesn't special-case per event type, it just records what
    already happened, the same "reacts, doesn't decide" boundary as
    notification-service.
    """
    data = envelope.data
    actor_id = _actor_id(data)
    result = next((str(data[field]) for field in _RESULT_FIELDS if data.get(field)), None)
    if result is None:
        raise MalformedEventError(f"event data has none of {', '.join(_RESULT_FIELDS)}")

    return AuditLog(
        event_id=envelope.event_id,
        actor_id=actor_id,
        action=envelope.event_type.value.upper().replace(".", "_"),
        resource_type=_resource_type(envelope.event_type.value),
        resource_id=_resource_id(data),
        result=result,
        correlation_id=envelope.correlation_id,
        details={key: value for key, value in data.items() if key not in _LIFTED_FIELDS},
        occurred_at=envelope.occurred_at,
    )


async def persist_audit_log(envelope: EventEnvelope) -> None:
    """The Kafka consumer's message handler (app/main.py, via
    app/services/dispatch.py). Idempotent on `envelope.event_id` — a
    redelivered event (at-least-once, spec Section 14.1) is a no-op
    here, not a duplicate audit row.
    """
    audit_log = handle_domain_event(envelope)

    async with db_session.async_session_factory() as session:
        repository = AuditLogRepository(session)
        if await repository.exists_for_event(envelope.event_id):
            logger.info("event %s already audited; skipping", envelope.event_id)
            return

        session.add(audit_log)
        try:
            await session.commit()
        except IntegrityError:
            # Lost a race against another delivery of the same event —
            # the UNIQUE(event_id) constraint is the real guard, the
            # pre-check above is only the fast path.
            await session.rollback()
            logger.info("event %s audited concurrently; skipping", envelope.event_id)
