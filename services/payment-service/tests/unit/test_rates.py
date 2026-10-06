"""Exchange arithmetic: integer minor units in, integer minor units out,
Decimal in between, rounded down."""

from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from app.core.config import settings
from app.services import rates
from app.services.rates import Rates, RatesUnavailableError, convert


def _rates(**per_usd: str) -> Rates:
    return Rates(
        per_usd={code: Decimal(value) for code, value in per_usd.items()},
        updated_at=datetime(2026, 10, 6, tzinfo=UTC),
        fetched=0.0,
    )


RATES = _rates(USD="1", UZS="12000")


def test_converts_both_ways() -> None:
    to_usd = convert(1_200_000_00, "UZS", "USD", RATES)
    to_uzs = convert(100_00, "USD", "UZS", RATES)

    assert to_usd.destination_amount_minor == 100_00
    assert to_uzs.destination_amount_minor == 1_200_000_00
    assert to_uzs.rate == Decimal("12000")


def test_always_rounds_down_never_inventing_a_fraction_of_a_unit() -> None:
    # 999.99 UZS at 12,000 per dollar is 0.0833325 USD: 8 cents, not 8.3.
    assert convert(999_99, "UZS", "USD", RATES).destination_amount_minor == 8
    # One som short of a cent buys nothing.
    assert convert(119_99, "UZS", "USD", RATES).destination_amount_minor == 0
    assert convert(120_00, "UZS", "USD", RATES).destination_amount_minor == 1


def test_a_round_trip_never_makes_money() -> None:
    awkward = _rates(USD="1", UZS="11835.853217")
    for amount in (1, 99, 100_00, 123_456_78, 999_999_999_99):
        there = convert(amount, "UZS", "USD", awkward).destination_amount_minor
        back = convert(there, "USD", "UZS", awkward).destination_amount_minor if there else 0
        assert back <= amount


def test_no_float_error_on_amounts_floats_get_wrong() -> None:
    # 0.1 + 0.2 territory: exact in Decimal.
    exact = _rates(USD="1", UZS="3")
    assert convert(10, "USD", "UZS", exact).destination_amount_minor == 30
    assert convert(10**17, "USD", "UZS", exact).destination_amount_minor == 3 * 10**17


def test_a_currency_without_a_rate_cannot_be_exchanged() -> None:
    with pytest.raises(RatesUnavailableError):
        convert(100, "UZS", "USD", _rates(USD="1"))


def _provider(*responses: httpx.Response | Exception):
    queue = list(responses)
    calls: list[int] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        outcome = queue.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    return httpx.MockTransport(handle), calls


def _ok(uzs: float = 11835.85) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "result": "success",
            "time_last_update_unix": 1_791_158_551,
            "rates": {"USD": 1, "UZS": uzs, "BAD": "x", "ZERO": 0},
        },
    )


@pytest.fixture(autouse=True)
def _fresh_cache() -> None:
    rates.reset_cache()
    yield
    rates.reset_cache()


async def test_rates_are_fetched_once_and_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    transport, calls = _provider(_ok())
    monkeypatch.setattr(rates, "transport", transport)

    first = await rates.current_rates()
    second = await rates.current_rates()

    assert len(calls) == 1 and first is second
    # The provider's digits exactly, and nothing unusable.
    assert first.per_usd == {"USD": Decimal("1"), "UZS": Decimal("11835.85")}
    assert first.updated_at == datetime.fromtimestamp(1_791_158_551, UTC)


async def test_a_failed_refresh_keeps_trading_on_recent_rates_but_not_old_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    down = httpx.ConnectError("down")
    transport, calls = _provider(_ok(), down, down)
    monkeypatch.setattr(rates, "transport", transport)
    monkeypatch.setattr(settings, "exchange_rates_ttl_seconds", 0.0)

    fresh = await rates.current_rates()
    still = await rates.current_rates()  # refresh fails: yesterday's rates are fine
    assert still is fresh and len(calls) == 2

    monkeypatch.setattr(settings, "exchange_rates_max_age_seconds", -1.0)
    with pytest.raises(RatesUnavailableError):
        await rates.current_rates()  # too old to trade on


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500),
        httpx.Response(200, json={"result": "error"}),
        httpx.Response(200, json={"result": "success", "rates": {"UZS": 12000}}),
        httpx.Response(200, content=b"not json"),
    ],
    ids=["server error", "provider error", "no dollar base", "not json"],
)
async def test_with_no_rates_at_all_exchange_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, response: httpx.Response
) -> None:
    transport, _ = _provider(response)
    monkeypatch.setattr(rates, "transport", transport)

    with pytest.raises(RatesUnavailableError):
        await rates.current_rates()
