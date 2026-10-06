from fincore_common import parse_decimal_string

from app.core.exceptions import InvalidAmountError


def parse_positive_amount(amount: str, currency: str) -> int:
    """A decimal string from a request as minor units (ADR-0001), or
    InvalidAmountError: not a number, more decimals than the currency
    has, or not greater than zero. "0" parses, but no operation moves
    nothing, and the database refuses the row - which reached the
    customer as a 500 before this check existed."""
    try:
        amount_minor = parse_decimal_string(amount, currency)
    except ValueError as exc:
        raise InvalidAmountError(str(exc)) from exc
    if amount_minor <= 0:
        raise InvalidAmountError("the amount must be greater than zero")
    return amount_minor
