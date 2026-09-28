import ssl

import httpx
import pytest

from fincore_common.http import async_client


def _count_ca_bundle_loads(monkeypatch: pytest.MonkeyPatch) -> list[None]:
    """Loading the CA bundle is the expensive, event-loop-blocking part of
    building an SSL context — count how often it happens."""
    calls: list[None] = []
    original = ssl.SSLContext.load_verify_locations

    def spy(self: ssl.SSLContext, *args: object, **kwargs: object) -> None:
        calls.append(None)
        original(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(ssl.SSLContext, "load_verify_locations", spy)
    return calls


def test_async_client_never_rebuilds_the_ssl_context(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _count_ca_bundle_loads(monkeypatch)

    for _ in range(5):
        async_client(base_url="http://ledger", timeout=5.0)

    assert calls == []


def test_a_plain_client_would_rebuild_it_every_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """The control: proves the spy above can see the cost at all."""
    calls = _count_ca_bundle_loads(monkeypatch)

    for _ in range(3):
        httpx.AsyncClient(base_url="http://ledger", timeout=5.0)

    assert len(calls) >= 3


def test_explicit_arguments_still_win() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(204))

    client = async_client(verify=False, transport=transport)

    assert client._transport is transport


async def test_the_client_works_against_a_transport() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True}))

    async with async_client(base_url="http://svc", transport=transport) as client:
        response = await client.get("/ping")

    assert response.json() == {"ok": True}
