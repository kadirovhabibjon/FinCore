"""Consumer side of contracts/events: notification-service's own message
composition for every transfer event it subscribes to, fed the
contract's canonical example rather than a fixture this service wrote
for itself.
"""

from uuid import UUID

import pytest
from fincore_common import EventEnvelope, EventType

from app.services.messages import compose_messages, compose_transfer_message
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


@pytest.mark.parametrize(
    "event_type",
    [
        EventType.TRANSFER_COMPLETED,
        EventType.TRANSFER_FAILED,
        EventType.PAYMENT_COMPLETED,
        EventType.PAYMENT_FAILED,
        EventType.PAYMENT_REFUNDED,
    ],
)
def test_every_contract_example_tells_its_initiator_something_complete(
    event_type: EventType,
) -> None:
    """Both topics this service subscribes to, each event type on them."""
    envelope = EventEnvelope(
        event_type=event_type, producer="payment-service", data=event_example(event_type.value)
    )
    assert_valid_event(envelope.model_dump(mode="json"))

    messages = compose_messages(envelope)

    first = messages[0]
    assert first.recipient_user_id == UUID(envelope.data["initiator_user_id"])
    assert first.subject and envelope.data["reference"] in first.body
    assert first.params["reference"] == envelope.data["reference"]
    assert first.params["amount"].endswith(envelope.data["currency"])
    assert len({message.recipient_user_id for message in messages}) == len(messages)


@pytest.mark.parametrize(
    ("event_type", "told"),
    [
        (EventType.MONEY_REQUEST_CREATED, "payer_user_id"),
        (EventType.MONEY_REQUEST_DECLINED, "requester_user_id"),
    ],
)
def test_money_request_examples_tell_the_other_person(event_type: EventType, told: str) -> None:
    envelope = EventEnvelope(
        event_type=event_type, producer="payment-service", data=event_example(event_type.value)
    )
    assert_valid_event(envelope.model_dump(mode="json"))

    [message] = compose_messages(envelope)

    assert message.recipient_user_id == UUID(envelope.data[told])
    assert message.params["amount"].endswith(envelope.data["currency"])


@pytest.mark.parametrize("event_type", [EventType.EXCHANGE_COMPLETED, EventType.EXCHANGE_FAILED])
def test_exchange_examples_tell_the_customer_both_amounts(event_type: EventType) -> None:
    envelope = EventEnvelope(
        event_type=event_type, producer="payment-service", data=event_example(event_type.value)
    )
    assert_valid_event(envelope.model_dump(mode="json"))

    [message] = compose_messages(envelope)

    assert message.recipient_user_id == UUID(envelope.data["initiator_user_id"])
    assert "1,200,000.00 UZS" in message.body and "100.00 USD" in message.body
    assert message.params["amount"] == "1,200,000.00 UZS"
    assert message.params["received"] == "100.00 USD"
    if event_type == EventType.EXCHANGE_FAILED:
        assert (
            "Insufficient Funds" in message.body and "Your money is in your wallet" in message.body
        )
