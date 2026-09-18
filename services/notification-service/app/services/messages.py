from uuid import UUID

from fincore_common import EventEnvelope, EventType
from fincore_common.money import minor_to_decimal


class UnhandledEventTypeError(Exception):
    pass


def compose_transfer_message(envelope: EventEnvelope) -> tuple[UUID, str, str]:
    """Builds (recipient_user_id, subject, body) for a transfer.completed
    or transfer.failed event (spec Section 15's "Transfer completed"
    example). Raises for any other event type — a consumer subscribed
    only to the "transfers" topic should never see one, so this is a bug
    (a producer emitting something unexpected), not a case to silently
    ignore.
    """
    data = envelope.data
    recipient_user_id = UUID(data["initiator_user_id"])
    reference = data["reference"]
    amount = minor_to_decimal(data["amount_minor"], data["currency"])

    if envelope.event_type == EventType.TRANSFER_COMPLETED:
        subject = "Transfer completed"
        body = f"Your transfer {reference} of {amount} {data['currency']} completed successfully."
        return recipient_user_id, subject, body

    if envelope.event_type == EventType.TRANSFER_FAILED:
        subject = "Transfer failed"
        reason = data.get("failure_reason") or "an internal error"
        body = f"Your transfer {reference} of {amount} {data['currency']} failed: {reason}."
        return recipient_user_id, subject, body

    raise UnhandledEventTypeError(envelope.event_type)
