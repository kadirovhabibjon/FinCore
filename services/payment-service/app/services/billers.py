"""Service providers a customer can pay from a wallet: mobile operators,
internet, utilities, TV.

Each provider is a merchant that belongs to FinCore itself rather than
to a customer, so paying one is an ordinary payment: the same saga
(fraud check, hold, capture into MERCHANT_SETTLEMENT), the same history,
receipts, notifications, daily limit and card block. What this adds is
the catalogue and the account the payment is for (a phone number, a
contract login, a personal account number).

FinCore is not connected to any of these providers. A payment is taken
and recorded here and delivered nowhere; the web app and the assistant
say so. Connecting one means sending the paid amount and account to the
provider after capture - a consumer of `payment.completed`, not a change
to this module.

Adding a provider takes a migration as well as a line here: its merchant
row (payments.merchant_id is a foreign key). The id is derived from the
code, so the two can't drift; tests/integration/test_services.py checks
every provider below has its row.
"""

import enum
import re
import uuid
from dataclasses import dataclass

from app.core.exceptions import InvalidServiceAccountError

# Who the provider merchants belong to: nobody who can sign in.
SYSTEM_OWNER_ID = uuid.UUID("00000000-0000-4000-8000-00000000b111")
_NAMESPACE = uuid.UUID("6f1c0de5-b111-4e25-9c0a-5e21c1ce0001")


class Category(enum.StrEnum):
    MOBILE = "MOBILE"
    INTERNET = "INTERNET"
    UTILITIES = "UTILITIES"
    TV = "TV"


class AccountKind(enum.StrEnum):
    """What identifies the customer at the provider."""

    PHONE = "PHONE"  # an Uzbek mobile number
    LOGIN = "LOGIN"  # an internet contract's login
    ACCOUNT_NUMBER = "ACCOUNT_NUMBER"  # a personal account number


@dataclass(frozen=True)
class Biller:
    code: str
    category: Category
    name: str
    account_kind: AccountKind
    currency: str = "UZS"
    # 1,000.00 to 5,000,000.00 UZS: no provider takes less, and more
    # than this in one payment is a mistake more often than a bill.
    min_amount_minor: int = 100_000
    max_amount_minor: int = 500_000_000

    @property
    def merchant_id(self) -> uuid.UUID:
        return uuid.uuid5(_NAMESPACE, self.code)


CATALOG: tuple[Biller, ...] = (
    Biller("beeline", Category.MOBILE, "Beeline", AccountKind.PHONE),
    Biller("ucell", Category.MOBILE, "Ucell", AccountKind.PHONE),
    Biller("uzmobile", Category.MOBILE, "Uzmobile", AccountKind.PHONE),
    Biller("mobiuz", Category.MOBILE, "Mobiuz", AccountKind.PHONE),
    Biller("humans", Category.MOBILE, "Humans", AccountKind.PHONE),
    Biller("uzonline", Category.INTERNET, "Uzonline", AccountKind.LOGIN),
    Biller("turon-telecom", Category.INTERNET, "Turon Telecom", AccountKind.LOGIN),
    Biller("sarkor-telecom", Category.INTERNET, "Sarkor Telecom", AccountKind.LOGIN),
    Biller("comnet", Category.INTERNET, "Comnet", AccountKind.LOGIN),
    Biller("electricity", Category.UTILITIES, "Electricity", AccountKind.ACCOUNT_NUMBER),
    Biller("natural-gas", Category.UTILITIES, "Natural gas", AccountKind.ACCOUNT_NUMBER),
    Biller("cold-water", Category.UTILITIES, "Cold water", AccountKind.ACCOUNT_NUMBER),
    Biller("heating", Category.UTILITIES, "Heating and hot water", AccountKind.ACCOUNT_NUMBER),
    Biller("waste", Category.UTILITIES, "Waste collection", AccountKind.ACCOUNT_NUMBER),
    Biller("uzdigital-tv", Category.TV, "Uzdigital TV", AccountKind.ACCOUNT_NUMBER),
)
_BY_CODE = {biller.code: biller for biller in CATALOG}


def find(code: str) -> Biller | None:
    return _BY_CODE.get(code)


_LOGIN = re.compile(r"[A-Za-z0-9._-]{4,32}")


def clean_account(biller: Biller, raw: str) -> str:
    """The account as it is recorded, or InvalidServiceAccountError.

    PHONE: an Uzbek mobile number however it was typed, stored as
    +998XXXXXXXXX. ACCOUNT_NUMBER: 6 to 14 digits, spaces and dashes
    dropped. LOGIN: 4 to 32 letters, digits, dots, dashes, underscores.
    """
    text = raw.strip()
    if biller.account_kind is AccountKind.PHONE:
        digits = re.sub(r"\D", "", text)
        if len(digits) == 12 and digits.startswith("998"):
            digits = digits[3:]
        if len(digits) != 9:
            raise InvalidServiceAccountError("enter a phone number like +998 90 123 45 67")
        return f"+998{digits}"
    if biller.account_kind is AccountKind.ACCOUNT_NUMBER:
        digits = re.sub(r"[\s-]", "", text)
        if not (digits.isascii() and digits.isdigit() and 6 <= len(digits) <= 14):
            raise InvalidServiceAccountError("an account number has 6 to 14 digits")
        return digits
    if not _LOGIN.fullmatch(text):
        raise InvalidServiceAccountError(
            "a login has 4 to 32 letters, digits, dots, dashes or underscores"
        )
    return text
