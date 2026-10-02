"""One canonical form for phone numbers: "+" and the full international
number, digits only ("+998901234567").

People type numbers many ways ("+998 90 123-45-67", "998901234567",
"90 123 45 67", "901234567"); storing and comparing the canonical form is
what lets a number be used to sign in however it's typed.
"""

import re

UZBEKISTAN = "998"
_LOCAL_LENGTH = 9  # Uzbek numbers without the country code: 90 123 45 67


class InvalidPhoneError(ValueError):
    pass


def normalize_phone(raw: str) -> str:
    """Canonical form of `raw`, or InvalidPhoneError. A 9-digit number is
    taken as Uzbek (the country code is added); anything else must carry
    its country code. Leading "00" counts as "+"."""
    text = raw.strip()
    digits = re.sub(r"\D", "", text)
    if text.startswith("00"):
        digits = digits[2:]
    if len(digits) == _LOCAL_LENGTH:
        digits = UZBEKISTAN + digits
    if digits.startswith(UZBEKISTAN) and len(digits) != len(UZBEKISTAN) + _LOCAL_LENGTH:
        raise InvalidPhoneError("an Uzbek number has 9 digits after +998")
    # E.164: at most 15 digits; 8 is the shortest real-world national plan.
    if not 8 <= len(digits) <= 15:
        raise InvalidPhoneError("enter a phone number like +998 90 123 45 67")
    return f"+{digits}"
