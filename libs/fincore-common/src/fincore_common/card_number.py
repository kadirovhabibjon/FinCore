"""FinCore card numbers: the 16-digit number a customer gives someone
who wants to send them money, instead of a wallet's UUID.

They identify a FinCore wallet and nothing else - they are not payment
cards and belong to no card network. The prefix starts with 9, the range
ISO/IEC 7812 leaves to national assignment, so a FinCore number can never
collide with a real Visa, Mastercard, Uzcard or Humo card. The last
digit is a Luhn check digit, which catches a mistyped or swapped digit
before any lookup happens.
"""

import secrets

CARD_NUMBER_PREFIX = "9955"
CARD_NUMBER_LENGTH = 16


def _luhn_check_digit(payload: str) -> str:
    total = 0
    # Walking right to left, every second digit starting with the one
    # next to the (not yet appended) check digit is doubled.
    for index, char in enumerate(reversed(payload)):
        digit = int(char)
        if index % 2 == 0:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return str((10 - total % 10) % 10)


def generate_card_number() -> str:
    body_length = CARD_NUMBER_LENGTH - len(CARD_NUMBER_PREFIX) - 1
    body = "".join(secrets.choice("0123456789") for _ in range(body_length))
    payload = CARD_NUMBER_PREFIX + body
    return payload + _luhn_check_digit(payload)


def normalize_card_number(value: str) -> str:
    """The digits of a number typed with spaces or dashes ("9955 1234 ...")."""
    return value.replace(" ", "").replace("-", "")


def is_valid_card_number(value: str) -> bool:
    """Whether `value` (already normalized) is a well-formed FinCore card
    number. Says nothing about whether a wallet with it exists."""
    return (
        len(value) == CARD_NUMBER_LENGTH
        and value.isascii()
        and value.isdigit()
        and value.startswith(CARD_NUMBER_PREFIX)
        and _luhn_check_digit(value[:-1]) == value[-1]
    )
