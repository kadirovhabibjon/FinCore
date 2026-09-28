"""Consumer side of contracts/events: notification-service's own message
composition for every transfer event it subscribes to, fed the
contract's canonical example rather than a fixture this service wrote
for itself.
"""

from uuid import UUID

import pytest
from fincore_common import EventEnvelope, EventType

from app.services.messages import compose_transfer_message
from tests.contracts import assert_valid_event, event_example


@pytest.mark.parametrize("event_type", [EventType.TRANSFER_COMPLETED, EventType.TRANSFER_FAILED])
def test_every_subscribed_event_can_be_turned_into_a_notification(event_type: EventType) -> None:
    envelope = EventEnvelope(
        event_type=event_type, producer="payment-service", data=event_example(event_type.value)
    )
    assert_valid_event(envelope.model_dump(mode="json"))

    recipient, subject, body = compose_transfer_message(envelope)

    assert recipient == UUID(envelope.data["initiator_user_id"])
    assert subject
    assert envelope.data["reference"] in body
