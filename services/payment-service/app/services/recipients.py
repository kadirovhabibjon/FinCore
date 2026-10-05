"""Finding who a transfer would go to from the card number the sender
typed, so they can check the name before sending."""

import logging
from dataclasses import dataclass
from uuid import UUID

from fincore_common import is_valid_card_number, normalize_card_number

from app.core.exceptions import (
    InvalidCardNumberError,
    RecipientLookupUnavailableError,
    RecipientNotFoundError,
)
from app.services import identity, ledger

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Recipient:
    wallet_id: UUID
    currency: str
    display_name: str
    # The card is one of the caller's own wallets.
    own: bool


def display_name(first_name: str, last_name: str) -> str:
    """"Aziza K." - enough for the sender to recognise who they meant,
    without handing a stranger's full name to anyone who tries a number."""
    first = first_name.strip()
    initial = last_name.strip()[:1].upper()
    return f"{first} {initial}." if initial else first


async def find_recipient(card_number: str, *, caller_user_id: UUID) -> Recipient:
    number = normalize_card_number(card_number)
    if not is_valid_card_number(number):
        raise InvalidCardNumberError("check the card number: 16 digits, starting with 9955")

    try:
        wallet = await ledger.ledger_client.find_wallet_by_card(number)
        if wallet is None or wallet.status != "ACTIVE":
            raise RecipientNotFoundError("no wallet can receive money at this card number")
        owner = await identity.identity_client.get_user(wallet.owner_user_id)
    except (ledger.LedgerUnavailableError, identity.IdentityUnavailableError) as exc:
        logger.warning("recipient lookup failed: %s", exc)
        raise RecipientLookupUnavailableError(
            "Can't look up the recipient right now. Try again shortly."
        ) from exc

    if owner is None or owner.status != "ACTIVE":
        raise RecipientNotFoundError("no wallet can receive money at this card number")
    return Recipient(
        wallet_id=wallet.id,
        currency=wallet.currency,
        display_name=display_name(owner.first_name, owner.last_name),
        own=wallet.owner_user_id == caller_user_id,
    )
