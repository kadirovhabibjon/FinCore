"""What to tell whom about an event: the English text (kept as the
fallback and for the mock email/SMS/push channels) and, next to it, the
facts it was built from, so the web app can say the same thing in the
reader's language.
"""

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from fincore_common import EventEnvelope, EventType
from fincore_common.money import minor_to_decimal

# Not event types: the other person's side of an event.
TRANSFER_RECEIVED = "transfer.received"
PAYMENT_RECEIVED = "payment.received"


class UnhandledEventTypeError(Exception):
    pass


@dataclass(frozen=True)
class Message:
    recipient_user_id: UUID
    notification_type: str
    subject: str
    body: str
    params: dict[str, Any] = field(default_factory=dict)


def _amount(data: dict) -> str:
    return f"{minor_to_decimal(data['amount_minor'], data['currency']):,} {data['currency']}"


def _facts(data: dict, **extra: Any) -> dict[str, Any]:
    """The parts of an event a notification's text is made of. `amount`
    is already formatted with its currency: clients show it as is."""
    facts = {"amount": _amount(data), "reference": data["reference"], **extra}
    return {key: value for key, value in facts.items() if value is not None}


def compose_transfer_message(envelope: EventEnvelope) -> tuple[UUID, str, str]:
    """Builds (recipient_user_id, subject, body) for the *sender* of a
    transfer.completed or transfer.failed event (spec Section 15's
    "Transfer completed" example). Raises for any other event type.
    """
    data = envelope.data
    recipient_user_id = UUID(data["initiator_user_id"])
    reference = data["reference"]
    amount = _amount(data)

    if envelope.event_type == EventType.TRANSFER_COMPLETED:
        subject = "Transfer completed"
        to = data.get("recipient_name")
        if to:
            body = f"You sent {amount} to {to} — reference {reference}"
        else:
            body = f"Your transfer {reference} of {amount} completed successfully."
        return recipient_user_id, subject, body

    if envelope.event_type == EventType.TRANSFER_FAILED:
        subject = "Transfer failed"
        reason = data.get("failure_reason") or "an internal error"
        to = data.get("recipient_name")
        target = f" to {to}" if to else ""
        body = f"Your transfer {reference} of {amount}{target} failed: {reason}."
        return recipient_user_id, subject, body

    raise UnhandledEventTypeError(envelope.event_type)


def _transfer_messages(envelope: EventEnvelope) -> list[Message]:
    """Always the sender, and for a completed transfer the person who
    received the money, when the event says who that is (older events,
    and transfers whose recipient couldn't be looked up, don't)."""
    data = envelope.data
    sender_id, subject, body = compose_transfer_message(envelope)
    messages = [
        Message(
            sender_id,
            envelope.event_type.value,
            subject,
            body,
            _facts(
                data,
                counterparty=data.get("recipient_name"),
                reason=data.get("failure_reason")
                if envelope.event_type == EventType.TRANSFER_FAILED
                else None,
            ),
        )
    ]

    recipient = data.get("recipient_user_id")
    if envelope.event_type == EventType.TRANSFER_COMPLETED and recipient:
        recipient_id = UUID(recipient)
        if recipient_id != sender_id:
            sender = data.get("sender_name")
            amount = _amount(data)
            received = f"{sender} sent you {amount}." if sender else f"You received {amount}."
            messages.append(
                Message(
                    recipient_id,
                    TRANSFER_RECEIVED,
                    "Money received",
                    received,
                    _facts(data, counterparty=sender),
                )
            )
    return messages


def _payment_messages(envelope: EventEnvelope) -> list[Message]:
    """The payer is told how their payment ended (paid, failed, expired,
    refunded); the merchant's owner is told when one is paid to them."""
    data = envelope.data
    payer_id = UUID(data["initiator_user_id"])
    reference = data["reference"]
    amount = _amount(data)
    merchant = data.get("merchant_name")
    to_merchant = f" to {merchant}" if merchant else ""
    event_type = envelope.event_type

    if event_type == EventType.PAYMENT_COMPLETED:
        messages = [
            Message(
                payer_id,
                event_type.value,
                "Payment completed",
                f"You paid {amount}{to_merchant} — reference {reference}",
                _facts(data, counterparty=merchant),
            )
        ]
        owner = data.get("merchant_owner_user_id")
        if owner and UUID(owner) != payer_id:
            messages.append(
                Message(
                    UUID(owner),
                    PAYMENT_RECEIVED,
                    "Payment received",
                    f"{merchant or 'Your merchant'} received a payment of {amount}"
                    f" — reference {reference}",
                    _facts(data, counterparty=merchant),
                )
            )
        return messages

    if event_type == EventType.PAYMENT_FAILED:
        if data.get("status") == "EXPIRED":
            reason = "it was not approved in time"
        else:
            reason = data.get("failure_reason") or "an internal error"
        return [
            Message(
                payer_id,
                event_type.value,
                "Payment failed",
                f"Your payment {reference} of {amount}{to_merchant} failed: {reason}."
                " No money was taken.",
                _facts(data, counterparty=merchant, reason=reason),
            )
        ]

    if event_type == EventType.PAYMENT_REFUNDED:
        partly = data.get("status") == "PARTIALLY_REFUNDED"
        how = "partly refunded" if partly else "refunded"
        by = f" by {merchant}" if merchant else ""
        return [
            Message(
                payer_id,
                event_type.value,
                "Refund received",
                f"Your payment {reference} of {amount} was {how}{by}."
                " The money is back in your wallet.",
                _facts(data, counterparty=merchant, partial=partly),
            )
        ]

    raise UnhandledEventTypeError(event_type)


def _money_request_messages(envelope: EventEnvelope) -> list[Message]:
    """A new request tells the person asked; a declined one tells the
    person who asked. (A paid one is a transfer, and is told as one.)"""
    data = envelope.data
    amount = _amount(data)
    note = data.get("note")

    if envelope.event_type == EventType.MONEY_REQUEST_CREATED:
        requester = data.get("requester_name")
        who = requester or "Someone"
        words = f": \u201c{note}\u201d" if note else ""
        return [
            Message(
                UUID(data["payer_user_id"]),
                envelope.event_type.value,
                "Money request",
                f"{who} asks you for {amount}{words}. Open Requests to pay or decline.",
                _facts(data, counterparty=requester, note=note),
            )
        ]

    if envelope.event_type == EventType.MONEY_REQUEST_DECLINED:
        payer = data.get("payer_name")
        return [
            Message(
                UUID(data["requester_user_id"]),
                envelope.event_type.value,
                "Request declined",
                f"{payer or 'The person you asked'} declined your request for {amount}.",
                _facts(data, counterparty=payer),
            )
        ]

    raise UnhandledEventTypeError(envelope.event_type)


def _exchange_messages(envelope: EventEnvelope) -> list[Message]:
    """The customer is told how their own exchange ended."""
    data = envelope.data
    sold = (
        f"{minor_to_decimal(data['source_amount_minor'], data['source_currency']):,}"
        f" {data['source_currency']}"
    )
    bought = (
        f"{minor_to_decimal(data['destination_amount_minor'], data['destination_currency']):,}"
        f" {data['destination_currency']}"
    )
    facts: dict[str, Any] = {"amount": sold, "received": bought, "reference": data["reference"]}
    user_id = UUID(data["initiator_user_id"])

    if envelope.event_type == EventType.EXCHANGE_COMPLETED:
        return [
            Message(
                user_id,
                envelope.event_type.value,
                "Exchange completed",
                f"You exchanged {sold} for {bought} — reference {data['reference']}",
                facts,
            )
        ]

    if envelope.event_type == EventType.EXCHANGE_FAILED:
        reason = data.get("failure_reason") or "an internal error"
        return [
            Message(
                user_id,
                envelope.event_type.value,
                "Exchange failed",
                f"Your exchange of {sold} for {bought} did not go through: {reason}."
                " Your money is in your wallet.",
                {**facts, "reason": reason},
            )
        ]

    raise UnhandledEventTypeError(envelope.event_type)


_TRANSFER_EVENTS = frozenset({EventType.TRANSFER_COMPLETED, EventType.TRANSFER_FAILED})
_PAYMENT_EVENTS = frozenset(
    {EventType.PAYMENT_COMPLETED, EventType.PAYMENT_FAILED, EventType.PAYMENT_REFUNDED}
)


_MONEY_REQUEST_EVENTS = frozenset(
    {EventType.MONEY_REQUEST_CREATED, EventType.MONEY_REQUEST_DECLINED}
)


_EXCHANGE_EVENTS = frozenset({EventType.EXCHANGE_COMPLETED, EventType.EXCHANGE_FAILED})


def compose_messages(envelope: EventEnvelope) -> list[Message]:
    """Everyone to tell about an event from the `transfers` or `payments`
    topic. Raises UnhandledEventTypeError for anything else: this
    consumer subscribes to nothing else, so that would be a producer
    emitting something unexpected, not a case to ignore silently."""
    if envelope.event_type in _TRANSFER_EVENTS:
        return _transfer_messages(envelope)
    if envelope.event_type in _PAYMENT_EVENTS:
        return _payment_messages(envelope)
    if envelope.event_type in _MONEY_REQUEST_EVENTS:
        return _money_request_messages(envelope)
    if envelope.event_type in _EXCHANGE_EVENTS:
        return _exchange_messages(envelope)
    raise UnhandledEventTypeError(envelope.event_type)
