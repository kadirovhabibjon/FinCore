"""Consumer side of contracts/events: audit-service's mapping of every
event it subscribes to (both topics), fed the contract's canonical
example rather than a fixture this service wrote for itself.
"""

from uuid import UUID

import pytest
from fincore_common import EventEnvelope, EventType

from app.services.consumer import handle_domain_event
from tests.contracts import assert_valid_event, event_example


@pytest.mark.parametrize("event_type", list(EventType))
def test_every_published_event_type_can_be_audited(event_type: EventType) -> None:
    envelope = EventEnvelope(
        event_type=event_type, producer="any", data=event_example(event_type.value)
    )
    assert_valid_event(envelope.model_dump(mode="json"))

    audit_log = handle_domain_event(envelope)

    assert audit_log.action == event_type.value.upper().replace(".", "_")
    actor = envelope.data.get("initiator_user_id") or envelope.data.get("actor_user_id")
    assert audit_log.actor_id == (UUID(actor) if actor else None)
    assert audit_log.result == envelope.data.get("status") or envelope.data["decision"]
    assert audit_log.resource_id == (
        envelope.data.get("transfer_id")
        or envelope.data.get("payment_id")
        or envelope.data.get("request_id")
        or envelope.data.get("exchange_id")
        or envelope.data.get("operation_id")
        or envelope.data.get("user_id")
    )
