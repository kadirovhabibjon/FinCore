"""Consumer side of contracts/events: webhook-service's own parsing of
every payment event it subscribes to, fed the contract's canonical
example rather than a fixture this service wrote for itself — so if
payment-service's payload changes (and its contract with it), this
breaks here instead of in production.
"""

from uuid import UUID

import pytest
from fincore_common import EventEnvelope, EventType

from app.services.consumer import _build_outbound_payload
from tests.contracts import assert_valid_event, event_example


@pytest.mark.parametrize(
    "event_type",
    [EventType.PAYMENT_COMPLETED, EventType.PAYMENT_FAILED, EventType.PAYMENT_REFUNDED],
)
def test_every_subscribed_event_can_be_turned_into_a_webhook(event_type: EventType) -> None:
    envelope = EventEnvelope(
        event_type=event_type, producer="payment-service", data=event_example(event_type.value)
    )
    assert_valid_event(envelope.model_dump(mode="json"))

    payload = _build_outbound_payload(envelope)
    # handle_payment_event's own routing key — every endpoint lookup
    # depends on it being present and a UUID.
    merchant_id = UUID(envelope.data["merchant_id"])

    assert merchant_id
    assert payload["event"] == event_type.value
    assert payload["event_id"] == str(envelope.event_id)
    assert payload["payment_id"] == envelope.data["payment_id"]
    assert payload["status"] == envelope.data["status"]
