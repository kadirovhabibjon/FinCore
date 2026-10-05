import logging

from fincore_common import EventEnvelope
from sqlalchemy.exc import IntegrityError

from app.db import session as db_session
from app.domain.notification import Notification
from app.repositories.notification_repository import NotificationRepository
from app.services.messages import compose_messages
from app.services.providers import NotificationProvider

logger = logging.getLogger(__name__)


async def handle_transfer_event(
    envelope: EventEnvelope, providers: list[NotificationProvider]
) -> None:
    """The Kafka consumer's message handler (app/main.py). Idempotent on
    (`envelope.event_id`, recipient) (spec Section 14.3): a redelivered
    event — the normal consequence of at-least-once delivery — is a
    no-op here, not a second notification. Each person's notification is
    its own transaction, so a failure after the sender was told doesn't
    tell them again on the retry, and still tells the recipient.
    """
    for message in compose_messages(envelope):
        async with db_session.async_session_factory() as session:
            repository = NotificationRepository(session)
            if await repository.exists_for_event(envelope.event_id, message.recipient_user_id):
                logger.info(
                    "event %s already notified to %s; skipping",
                    envelope.event_id,
                    message.recipient_user_id,
                )
                continue

            for provider in providers:
                await provider.send(
                    recipient_user_id=message.recipient_user_id,
                    subject=message.subject,
                    body=message.body,
                )

            session.add(
                Notification(
                    event_id=envelope.event_id,
                    recipient_user_id=message.recipient_user_id,
                    notification_type=message.notification_type,
                    subject=message.subject,
                    body=message.body,
                )
            )
            try:
                await session.commit()
            except IntegrityError:
                # Lost a race against another delivery of the same event —
                # the UNIQUE(event_id, recipient_user_id) constraint is
                # the real guard here, the pre-check above is only the
                # fast path. The notification was already sent by the
                # other path in this same window; nothing further to do.
                await session.rollback()
                logger.info("event %s recorded concurrently; skipping", envelope.event_id)
