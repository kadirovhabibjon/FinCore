from dataclasses import dataclass
from uuid import UUID

from fincore_common import EventEnvelope, EventType
from fincore_common.money import minor_to_decimal

# Not an event type: the recipient's side of a transfer.completed event.
TRANSFER_RECEIVED = "transfer.received"


class UnhandledEventTypeError(Exception):
    pass


@dataclass(frozen=True)
class Message:
    recipient_user_id: UUID
    notification_type: str
    subject: str
    body: str


def _amount(data: dict) -> str:
    return f"{minor_to_decimal(data['amount_minor'], data['currency']):,} {data['currency']}"


def compose_transfer_message(envelope: EventEnvelope) -> tuple[UUID, str, str]:
    """Builds (recipient_user_id, subject, body) for the *sender* of a
    transfer.completed or transfer.failed event (spec Section 15's
    "Transfer completed" example). Raises for any other event type — a
    consumer subscribed only to the "transfers" topic should never see
    one, so this is a bug (a producer emitting something unexpected),
    not a case to silently ignore.
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


def compose_messages(envelope: EventEnvelope) -> list[Message]:
    """Everyone to tell about a transfer event: always the sender, and
    for a completed transfer the person who received the money, when the
    event says who that is (older events, and transfers whose recipient
    couldn't be looked up, don't)."""
    sender_id, subject, body = compose_transfer_message(envelope)
    messages = [Message(sender_id, envelope.event_type.value, subject, body)]

    data = envelope.data
    recipient = data.get("recipient_user_id")
    if envelope.event_type == EventType.TRANSFER_COMPLETED and recipient:
        recipient_id = UUID(recipient)
        if recipient_id != sender_id:
            sender = data.get("sender_name")
            amount = _amount(data)
            received = f"{sender} sent you {amount}." if sender else f"You received {amount}."
            messages.append(Message(recipient_id, TRANSFER_RECEIVED, "Money received", received))
    return messages
