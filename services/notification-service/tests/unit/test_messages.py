import uuid

import pytest
from fincore_common import EventEnvelope, EventType

from app.services.messages import (
    UnhandledEventTypeError,
    compose_messages,
    compose_transfer_message,
)

_USER_ID = uuid.uuid4()


def _envelope(event_type: EventType, **data_overrides: object) -> EventEnvelope:
    data = {
        "transfer_id": str(uuid.uuid4()),
        "reference": "TRF-ABC123",
        "initiator_user_id": str(_USER_ID),
        "amount_minor": 150_00,
        "currency": "UZS",
        "status": "COMPLETED",
        "failure_reason": None,
        "completed_at": "2026-01-01T00:00:00Z",
    }
    data.update(data_overrides)
    return EventEnvelope(event_type=event_type, producer="payment-service", data=data)


def test_composes_a_completed_transfer_message() -> None:
    recipient, subject, body = compose_transfer_message(_envelope(EventType.TRANSFER_COMPLETED))

    assert recipient == _USER_ID
    assert subject == "Transfer completed"
    assert "TRF-ABC123" in body
    assert "150.00 UZS" in body


def test_composes_a_failed_transfer_message_with_the_reason() -> None:
    envelope = _envelope(EventType.TRANSFER_FAILED, failure_reason="insufficient funds")

    recipient, subject, body = compose_transfer_message(envelope)

    assert subject == "Transfer failed"
    assert "insufficient funds" in body


def test_a_failed_transfer_without_a_reason_still_composes_a_message() -> None:
    envelope = _envelope(EventType.TRANSFER_FAILED, failure_reason=None)

    _, _, body = compose_transfer_message(envelope)

    assert "an internal error" in body


def test_rejects_an_event_type_it_does_not_know_how_to_compose() -> None:
    """`EventType` only has two members today, but this guards against a
    silent no-op if a third one is ever added to the registry without
    teaching this function about it.
    """
    envelope = _envelope(EventType.TRANSFER_COMPLETED)
    envelope.event_type = "some.other.event"  # type: ignore[assignment]

    with pytest.raises(UnhandledEventTypeError):
        compose_transfer_message(envelope)


def test_a_completed_transfer_tells_the_sender_and_the_recipient_by_name() -> None:
    recipient = uuid.uuid4()
    envelope = _envelope(
        EventType.TRANSFER_COMPLETED,
        recipient_user_id=str(recipient),
        sender_name="Aziza K.",
        recipient_name="Bobur T.",
        amount_minor=1_250_000_00,
    )

    to_sender, to_recipient = compose_messages(envelope)

    assert to_sender.recipient_user_id == _USER_ID
    assert to_sender.notification_type == "transfer.completed"
    assert to_sender.body == "You sent 1,250,000.00 UZS to Bobur T. — reference TRF-ABC123"
    assert to_recipient.recipient_user_id == recipient
    assert to_recipient.notification_type == "transfer.received"
    assert to_recipient.subject == "Money received"
    assert to_recipient.body == "Aziza K. sent you 1,250,000.00 UZS."


def test_without_names_the_messages_still_read_properly() -> None:
    envelope = _envelope(EventType.TRANSFER_COMPLETED, recipient_user_id=str(uuid.uuid4()))

    to_sender, to_recipient = compose_messages(envelope)

    assert to_sender.body == "Your transfer TRF-ABC123 of 150.00 UZS completed successfully."
    assert to_recipient.body == "You received 150.00 UZS."


def test_only_the_sender_hears_about_a_failed_transfer_or_an_unknown_recipient() -> None:
    failed = _envelope(
        EventType.TRANSFER_FAILED,
        recipient_user_id=str(uuid.uuid4()),
        recipient_name="Bobur T.",
        failure_reason="Insufficient Funds",
    )
    # An event published before recipients were recorded.
    old = _envelope(EventType.TRANSFER_COMPLETED)

    [to_sender] = compose_messages(failed)
    assert to_sender.body == (
        "Your transfer TRF-ABC123 of 150.00 UZS to Bobur T. failed: Insufficient Funds."
    )
    assert len(compose_messages(old)) == 1


def _payment(event_type: EventType, **overrides: object) -> EventEnvelope:
    data = {
        "payment_id": str(uuid.uuid4()),
        "reference": "PAY-ABC123",
        "initiator_user_id": str(_USER_ID),
        "merchant_id": str(uuid.uuid4()),
        "merchant_name": "Choyxona",
        "merchant_owner_user_id": str(uuid.uuid4()),
        "amount_minor": 45_000_00,
        "currency": "UZS",
        "status": "SUCCESS",
        "failure_reason": None,
        "completed_at": "2026-01-01T00:00:00Z",
    }
    data.update(overrides)
    return EventEnvelope(event_type=event_type, producer="payment-service", data=data)


def test_a_completed_payment_tells_the_payer_and_the_merchants_owner() -> None:
    envelope = _payment(EventType.PAYMENT_COMPLETED)

    to_payer, to_merchant = compose_messages(envelope)

    assert to_payer.recipient_user_id == _USER_ID
    assert to_payer.notification_type == "payment.completed"
    assert to_payer.body == "You paid 45,000.00 UZS to Choyxona — reference PAY-ABC123"
    assert to_payer.params == {
        "amount": "45,000.00 UZS",
        "reference": "PAY-ABC123",
        "counterparty": "Choyxona",
    }
    assert str(to_merchant.recipient_user_id) == envelope.data["merchant_owner_user_id"]
    assert to_merchant.notification_type == "payment.received"
    assert to_merchant.subject == "Payment received"
    assert "Choyxona received a payment of 45,000.00 UZS" in to_merchant.body


def test_paying_your_own_merchant_is_one_notification_not_two() -> None:
    envelope = _payment(EventType.PAYMENT_COMPLETED, merchant_owner_user_id=str(_USER_ID))

    assert [m.notification_type for m in compose_messages(envelope)] == ["payment.completed"]


def test_a_payment_event_without_the_merchant_still_reads_properly() -> None:
    """Events published before the merchant was put on them."""
    envelope = _payment(EventType.PAYMENT_COMPLETED)
    del envelope.data["merchant_name"]
    del envelope.data["merchant_owner_user_id"]

    [to_payer] = compose_messages(envelope)

    assert to_payer.body == "You paid 45,000.00 UZS — reference PAY-ABC123"
    assert "counterparty" not in to_payer.params


def test_a_failed_or_expired_payment_says_why_and_that_nothing_was_taken() -> None:
    failed = _payment(
        EventType.PAYMENT_FAILED, status="FAILED", failure_reason="Insufficient Funds"
    )
    expired = _payment(EventType.PAYMENT_FAILED, status="EXPIRED")

    [why_failed] = compose_messages(failed)
    [why_expired] = compose_messages(expired)

    assert why_failed.subject == "Payment failed"
    assert why_failed.body == (
        "Your payment PAY-ABC123 of 45,000.00 UZS to Choyxona failed: Insufficient Funds."
        " No money was taken."
    )
    assert why_failed.params["reason"] == "Insufficient Funds"
    assert "it was not approved in time" in why_expired.body


def test_a_refund_tells_the_payer_whether_it_was_full_or_partial() -> None:
    full = _payment(EventType.PAYMENT_REFUNDED, status="REFUNDED")
    partial = _payment(EventType.PAYMENT_REFUNDED, status="PARTIALLY_REFUNDED")

    [whole] = compose_messages(full)
    [part] = compose_messages(partial)

    assert whole.notification_type == "payment.refunded"
    assert whole.subject == "Refund received"
    assert "was refunded by Choyxona" in whole.body and whole.params["partial"] is False
    assert "was partly refunded by Choyxona" in part.body and part.params["partial"] is True


def test_an_event_from_another_topic_is_refused() -> None:
    envelope = EventEnvelope(
        event_type=EventType.USER_REGISTERED, producer="identity-service", data={}
    )

    with pytest.raises(UnhandledEventTypeError):
        compose_messages(envelope)


def _request(event_type: EventType, **overrides: object) -> EventEnvelope:
    data = {
        "request_id": str(uuid.uuid4()),
        "reference": "REQ-ABC123",
        "requester_user_id": str(_USER_ID),
        "payer_user_id": str(uuid.uuid4()),
        "requester_name": "Aziza K.",
        "payer_name": "Bobur T.",
        "amount_minor": 50_000_00,
        "currency": "UZS",
        "note": "Dinner",
        "status": "PENDING",
    }
    data.update(overrides)
    return EventEnvelope(event_type=event_type, producer="payment-service", data=data)


def test_a_money_request_tells_the_person_asked_who_wants_how_much_and_why() -> None:
    envelope = _request(EventType.MONEY_REQUEST_CREATED)

    [message] = compose_messages(envelope)

    assert str(message.recipient_user_id) == envelope.data["payer_user_id"]
    assert message.notification_type == "money_request.created"
    assert message.subject == "Money request"
    assert message.body == (
        "Aziza K. asks you for 50,000.00 UZS: \u201cDinner\u201d. Open Requests to pay or decline."
    )
    assert message.params == {
        "amount": "50,000.00 UZS",
        "reference": "REQ-ABC123",
        "counterparty": "Aziza K.",
        "note": "Dinner",
    }


def test_a_request_without_a_note_or_a_name_still_reads_properly() -> None:
    envelope = _request(EventType.MONEY_REQUEST_CREATED, note=None, requester_name=None)

    [message] = compose_messages(envelope)

    assert message.body == "Someone asks you for 50,000.00 UZS. Open Requests to pay or decline."


def test_a_declined_request_tells_the_person_who_asked() -> None:
    envelope = _request(EventType.MONEY_REQUEST_DECLINED, status="DECLINED")

    [message] = compose_messages(envelope)

    assert message.recipient_user_id == _USER_ID
    assert message.subject == "Request declined"
    assert message.body == "Bobur T. declined your request for 50,000.00 UZS."
