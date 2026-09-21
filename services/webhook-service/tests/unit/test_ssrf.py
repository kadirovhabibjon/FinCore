import socket

import pytest

from app.core.exceptions import InvalidWebhookUrlError
from app.services import ssrf


def _fake_getaddrinfo(addresses: list[str]):
    def _impl(host, port, proto=0):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (addr, 0)) for addr in addresses]

    return _impl


async def test_rejects_unsupported_scheme() -> None:
    with pytest.raises(InvalidWebhookUrlError):
        await ssrf.assert_safe_url("ftp://example.com/hook")


async def test_rejects_malformed_url_without_hostname() -> None:
    with pytest.raises(InvalidWebhookUrlError):
        await ssrf.assert_safe_url("https:///no-host")


async def test_rejects_loopback_address(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ssrf.socket, "getaddrinfo", _fake_getaddrinfo(["127.0.0.1"]))
    with pytest.raises(InvalidWebhookUrlError):
        await ssrf.assert_safe_url("http://localhost/hook")


async def test_rejects_private_network_address(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ssrf.socket, "getaddrinfo", _fake_getaddrinfo(["10.0.0.5"]))
    with pytest.raises(InvalidWebhookUrlError):
        await ssrf.assert_safe_url("http://internal.example.com/hook")


async def test_rejects_link_local_metadata_address(monkeypatch: pytest.MonkeyPatch) -> None:
    # 169.254.169.254 — the classic cloud-metadata SSRF target.
    monkeypatch.setattr(ssrf.socket, "getaddrinfo", _fake_getaddrinfo(["169.254.169.254"]))
    with pytest.raises(InvalidWebhookUrlError):
        await ssrf.assert_safe_url("http://metadata.example.com/hook")


async def test_rejects_when_any_resolved_address_is_private(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    addresses = ["93.184.216.34", "10.0.0.1"]
    monkeypatch.setattr(ssrf.socket, "getaddrinfo", _fake_getaddrinfo(addresses))
    with pytest.raises(InvalidWebhookUrlError):
        await ssrf.assert_safe_url("http://mixed.example.com/hook")


async def test_allows_a_public_address(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ssrf.socket, "getaddrinfo", _fake_getaddrinfo(["93.184.216.34"]))
    await ssrf.assert_safe_url("https://merchant.example.com/webhooks")


async def test_rejects_unresolvable_host(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(host, port, proto=0):
        raise socket.gaierror("nope")

    monkeypatch.setattr(ssrf.socket, "getaddrinfo", _raise)
    with pytest.raises(InvalidWebhookUrlError):
        await ssrf.assert_safe_url("https://does-not-resolve.invalid/hook")
