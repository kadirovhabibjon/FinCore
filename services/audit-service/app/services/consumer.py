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
    {"transfer_id", "payment_id", "initiator_user_id", "status", "reference"}
)


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
    resource_id = data.get("transfer_id") or data.get("payment_id")
    if not resource_id:
        raise MalformedEventError("event data has neither transfer_id nor payment_id")
    return str(resource_id)


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
    try:
        actor_id = UUID(data["initiator_user_id"]) if data.get("initiator_user_id") else None
        result = data["status"]
    except KeyError as exc:
        raise MalformedEventError(f"event missing required field: {exc}") from exc

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
