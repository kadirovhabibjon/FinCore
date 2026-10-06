"""Who is on each side of a transfer: recorded when it is created so
the recipient can be shown it in their history and told about it, and
so each side sees a name instead of a wallet id.

Best effort by design. A transfer never fails or waits long because a
name couldn't be fetched: whatever is unknown is stored as NULL, and the
money still moves. The lookups run before the transfer exists, so they
can't leave anything half done.
"""

import asyncio
import logging
from dataclasses import dataclass
from uuid import UUID

from app.services import identity, ledger
from app.services.recipients import display_name

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TransferParties:
    recipient_user_id: UUID | None = None
    sender_name: str | None = None
    recipient_name: str | None = None
    recipient_card_number: str | None = None


async def _name_of(user_id: UUID) -> str | None:
    user = await identity.identity_client.get_user(user_id)
    return display_name(user.first_name, user.last_name) if user else None


@dataclass(frozen=True)
class _Recipient:
    user_id: UUID | None = None
    name: str | None = None
    card_number: str | None = None


async def _recipient_of(wallet_id: UUID) -> _Recipient:
    wallet = await ledger.ledger_client.find_wallet_owner(wallet_id)
    if wallet is None:
        return _Recipient()
    try:
        name = await _name_of(wallet.owner_user_id)
    except Exception as exc:  # the owner is still worth recording without a name
        logger.warning("recipient name lookup failed: %s", exc)
        name = None
    return _Recipient(user_id=wallet.owner_user_id, name=name, card_number=wallet.card_number)


async def resolve_parties(
    *, initiator_user_id: UUID, destination_wallet_id: UUID
) -> TransferParties:
    sender, recipient = await asyncio.gather(
        _name_of(initiator_user_id), _recipient_of(destination_wallet_id), return_exceptions=True
    )
    if isinstance(sender, BaseException):
        logger.warning("sender name lookup failed: %s", sender)
        sender = None
    if isinstance(recipient, BaseException):
        logger.warning("recipient lookup failed: %s", recipient)
        recipient = _Recipient()
    return TransferParties(
        recipient_user_id=recipient.user_id,
        sender_name=sender,
        recipient_name=recipient.name,
        recipient_card_number=recipient.card_number,
    )
