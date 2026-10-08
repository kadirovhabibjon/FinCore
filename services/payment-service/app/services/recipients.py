"""Finding who a transfer would go to from the card number or phone
number the sender typed, so they can check the name before sending."""

import logging
from dataclasses import dataclass
from uuid import UUID

from fincore_common import is_valid_card_number, normalize_card_number

from app.core.exceptions import (
    InvalidCardNumberError,
    InvalidPhoneNumberError,
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
    # Never sent to a browser: for services that act on the lookup.
    owner_user_id: UUID | None = None
    # The end of the card the money would go to: with a phone number the
    # sender never typed a card, and this is what tells them which one.
    card_last4: str | None = None


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
        owner_user_id=wallet.owner_user_id,
        card_last4=number[-4:],
    )


async def find_recipient_by_phone(phone: str, currency: str, *, caller_user_id: UUID) -> Recipient:
    """The wallet money sent to this phone number would reach: its
    owner's wallet in the sender's currency (a customer has at most one
    per currency). One "not found" for a number nobody registered, an
    account that isn't active, and a person with no usable wallet in
    that currency - the same reasoning as for card numbers."""
    nobody = RecipientNotFoundError(f"nobody can receive {currency} at this phone number")
    try:
        owner = await identity.identity_client.find_user_by_phone(phone)
        if owner is None or owner.id is None or owner.status != "ACTIVE":
            raise nobody
        wallet = await ledger.ledger_client.find_wallet_of(owner.id, currency)
    except identity.InvalidPhoneError as exc:
        raise InvalidPhoneNumberError(str(exc)) from exc
    except (ledger.LedgerUnavailableError, identity.IdentityUnavailableError) as exc:
        logger.warning("recipient lookup failed: %s", exc)
        raise RecipientLookupUnavailableError(
            "Can't look up the recipient right now. Try again shortly."
        ) from exc

    if wallet is None or wallet.status != "ACTIVE":
        raise nobody
    return Recipient(
        wallet_id=wallet.id,
        currency=wallet.currency,
        display_name=display_name(owner.first_name, owner.last_name),
        own=wallet.owner_user_id == caller_user_id,
        owner_user_id=wallet.owner_user_id,
        card_last4=wallet.card_number[-4:] if wallet.card_number else None,
    )
