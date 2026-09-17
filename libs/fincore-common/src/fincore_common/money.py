from decimal import Decimal, InvalidOperation

# Minor-unit exponent per supported currency (ISO 4217). Spec Section 6.2:
# v1 supports these two, same-currency operations only. Adding a currency
# here is the one place that decision is made.
SUPPORTED_CURRENCIES: dict[str, int] = {
    "UZS": 2,
    "USD": 2,
}


class UnsupportedCurrencyError(ValueError):
    pass


class InvalidAmountError(ValueError):
    pass


def minor_unit_exponent(currency: str) -> int:
    try:
        return SUPPORTED_CURRENCIES[currency]
    except KeyError:
        raise UnsupportedCurrencyError(currency) from None


def decimal_to_minor(amount: Decimal, currency: str) -> int:
    """Converts a Decimal major-unit amount to an integer minor-unit
    amount (ADR-0001). Rejects anything with more precision than the
    currency supports rather than silently rounding — a caller sending
    "10.005" for a 2-decimal currency has a bug, and this surfaces it
    instead of quietly losing half a cent.
    """
    exponent = minor_unit_exponent(currency)
    scaled = amount * (10**exponent)
    if scaled != scaled.to_integral_value():
        raise InvalidAmountError(f"{amount} has more precision than {currency} supports")
    return int(scaled)


def minor_to_decimal(amount_minor: int, currency: str) -> Decimal:
    exponent = minor_unit_exponent(currency)
    return Decimal(amount_minor).scaleb(-exponent)


def parse_decimal_string(value: str, currency: str) -> int:
    """The public-API boundary parser (ADR-0001): a decimal string in,
    minor units out. `float()` never appears anywhere in this path.
    """
    try:
        amount = Decimal(value)
    except InvalidOperation:
        raise InvalidAmountError(f"{value!r} is not a valid decimal amount") from None
    return decimal_to_minor(amount, currency)
