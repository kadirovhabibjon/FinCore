from decimal import Decimal

import pytest

from fincore_common.money import (
    InvalidAmountError,
    UnsupportedCurrencyError,
    decimal_to_minor,
    minor_to_decimal,
    minor_unit_exponent,
    parse_decimal_string,
)


def test_minor_unit_exponent_known_currencies() -> None:
    assert minor_unit_exponent("UZS") == 2
    assert minor_unit_exponent("USD") == 2


def test_minor_unit_exponent_rejects_unsupported_currency() -> None:
    with pytest.raises(UnsupportedCurrencyError):
        minor_unit_exponent("EUR")


def test_decimal_to_minor_converts_exactly() -> None:
    assert decimal_to_minor(Decimal("100000.00"), "UZS") == 10_000_000
    assert decimal_to_minor(Decimal("1.50"), "USD") == 150
    assert decimal_to_minor(Decimal("0"), "USD") == 0


def test_decimal_to_minor_rejects_excess_precision_instead_of_rounding() -> None:
    with pytest.raises(InvalidAmountError):
        decimal_to_minor(Decimal("10.005"), "USD")


def test_minor_to_decimal_is_the_inverse_of_decimal_to_minor() -> None:
    original = Decimal("54321.99")
    assert minor_to_decimal(decimal_to_minor(original, "USD"), "USD") == original


def test_parse_decimal_string_accepts_a_well_formed_string() -> None:
    assert parse_decimal_string("100000.00", "UZS") == 10_000_000


def test_parse_decimal_string_rejects_garbage_input() -> None:
    with pytest.raises(InvalidAmountError):
        parse_decimal_string("not-a-number", "USD")


def test_parse_decimal_string_never_goes_through_float() -> None:
    # A float can't exactly represent 0.1; if this path ever regressed to
    # `float(value)`, this amount would round-trip to the wrong integer.
    assert parse_decimal_string("0.10", "USD") == 10
