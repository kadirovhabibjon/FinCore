"""Exchange rates for converting between a customer's own wallets.

Money arithmetic here follows ADR-0001: amounts are integer minor
units, rates are Decimals (never floats), and the result is rounded
*down* to a whole minor unit, so an exchange can never hand out a
fraction of a unit that doesn't exist.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal, InvalidOperation

import httpx
from fincore_common import minor_unit_exponent

from app.core.config import settings

logger = logging.getLogger(__name__)

# Tests swap in an httpx.MockTransport.
transport: httpx.AsyncBaseTransport | None = None


class RatesUnavailableError(Exception):
    """No rates fresh enough to trade on."""


@dataclass(frozen=True)
class Rates:
    # Units of each currency per one US dollar.
    per_usd: dict[str, Decimal]
    # When the provider last updated them.
    updated_at: datetime
    # When this process fetched them (monotonic seconds).
    fetched: float


@dataclass(frozen=True)
class Conversion:
    destination_amount_minor: int
    # Units of the destination currency per one unit of the source.
    rate: Decimal


_cached: Rates | None = None
_lock = asyncio.Lock()


def reset_cache() -> None:
    """For tests."""
    global _cached
    _cached = None


async def _fetch() -> Rates:
    async with httpx.AsyncClient(
        timeout=settings.exchange_rates_timeout_seconds, transport=transport
    ) as client:
        response = await client.get(settings.exchange_rates_url)
    response.raise_for_status()
    data = response.json()
    if data.get("result") != "success":
        raise ValueError("the provider did not return rates")
    per_usd: dict[str, Decimal] = {}
    for code, value in (data.get("rates") or {}).items():
        try:
            # Through str: the exact digits the provider sent, not the
            # binary float they were parsed into.
            rate = Decimal(str(value))
        except InvalidOperation:
            continue
        if rate.is_finite() and rate > 0:
            per_usd[code] = rate
    if "USD" not in per_usd:
        raise ValueError("the provider's rates have no USD base")
    updated = data.get("time_last_update_unix")
    return Rates(
        per_usd=per_usd,
        updated_at=datetime.fromtimestamp(updated, UTC)
        if isinstance(updated, int)
        else datetime.now(UTC),
        fetched=time.monotonic(),
    )


async def current_rates() -> Rates:
    """The rates to trade on: cached ones while they are fresh, newly
    fetched ones otherwise; if fetching fails, the cached ones as long
    as they are not too old. Raises RatesUnavailableError beyond that."""
    global _cached
    now = time.monotonic()
    if _cached is not None and now - _cached.fetched < settings.exchange_rates_ttl_seconds:
        return _cached
    async with _lock:
        if _cached is not None and now - _cached.fetched < settings.exchange_rates_ttl_seconds:
            return _cached
        try:
            _cached = await _fetch()
        except Exception as exc:
            logger.warning("exchange rates could not be refreshed: %s", type(exc).__name__)
            stale = _cached
            if stale is None or now - stale.fetched > settings.exchange_rates_max_age_seconds:
                raise RatesUnavailableError("no usable exchange rates") from exc
        assert _cached is not None
        return _cached


def convert(amount_minor: int, source: str, destination: str, rates: Rates) -> Conversion:
    """What `amount_minor` of `source` buys in `destination`. Raises
    RatesUnavailableError if either currency has no rate."""
    try:
        source_per_usd = rates.per_usd[source]
        destination_per_usd = rates.per_usd[destination]
    except KeyError as exc:
        raise RatesUnavailableError(f"no rate for {exc.args[0]}") from exc
    rate = destination_per_usd / source_per_usd
    scale = Decimal(10) ** (minor_unit_exponent(destination) - minor_unit_exponent(source))
    bought = (Decimal(amount_minor) * rate * scale).to_integral_value(rounding=ROUND_DOWN)
    return Conversion(destination_amount_minor=int(bought), rate=rate)
