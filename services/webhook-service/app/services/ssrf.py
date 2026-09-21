import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

from app.core.exceptions import InvalidWebhookUrlError

_ALLOWED_SCHEMES = {"http", "https"}


def _is_public(ip_str: str) -> bool:
    ip = ipaddress.ip_address(ip_str)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


async def assert_safe_url(url: str) -> None:
    """SSRF protection (spec Section 17): rejects a non-http(s) scheme
    outright, then resolves the hostname and rejects any target that
    resolves to a private/loopback/link-local/reserved/multicast
    address — the classic "register a webhook pointed at
    169.254.169.254 or localhost:5432" attack.

    Called twice: once at registration time (app/services/endpoints.py,
    a fast rejection for the common case) and again immediately before
    every delivery attempt (app/services/delivery.py) — DNS can change
    between the two, so only the second check is the real guarantee.
    Every resolved address must be public, not just one of them: a
    hostname with a mixed public/private answer set could otherwise be
    used to reach the private one by whichever address the HTTP client
    happens to pick.
    """
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.hostname:
        raise InvalidWebhookUrlError(f"unsupported or malformed URL: {url}")

    try:
        infos = await asyncio.to_thread(
            socket.getaddrinfo, parsed.hostname, None, proto=socket.IPPROTO_TCP
        )
    except socket.gaierror as exc:
        raise InvalidWebhookUrlError(f"could not resolve host: {parsed.hostname}") from exc

    if not infos:
        raise InvalidWebhookUrlError(f"could not resolve host: {parsed.hostname}")

    for _family, _, _, _, sockaddr in infos:
        ip_str = str(sockaddr[0])
        if not _is_public(ip_str):
            raise InvalidWebhookUrlError(f"target address is not publicly routable: {ip_str}")
