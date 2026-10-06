"""Recognising the device a sign-in comes from, to tell the account's
owner about one they have not used before.

A "device" here is what the browser says about itself (its User-Agent)
with the version numbers removed, so a browser updating itself is not a
new device. It is a courtesy signal, not a security boundary: anyone can
send any User-Agent, and an attacker who copies the owner's gets no
email. What it catches is the common case - a sign-in from a different
browser or phone than the owner's.
"""

import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.session import Session

_VERSION = re.compile(r"[\d._]+")

_BROWSERS = (
    ("Edg", "Edge"),
    ("OPR", "Opera"),
    ("YaBrowser", "Yandex Browser"),
    ("SamsungBrowser", "Samsung Internet"),
    ("Firefox", "Firefox"),
    ("FxiOS", "Firefox"),
    ("CriOS", "Chrome"),
    ("Chrome", "Chrome"),
    ("Safari", "Safari"),
)
_SYSTEMS = (
    ("Android", "Android"),
    ("iPhone", "iPhone"),
    ("iPad", "iPad"),
    ("Windows", "Windows"),
    ("Mac OS X", "Mac"),
    ("Macintosh", "Mac"),
    ("CrOS", "ChromeOS"),
    ("Linux", "Linux"),
)


def device_signature(user_agent: str | None) -> str:
    """What makes two sign-ins "the same device": the User-Agent without
    its version numbers."""
    return _VERSION.sub("", user_agent or "").strip()


def describe_device(user_agent: str | None) -> str:
    """"Chrome on Windows" - for a person to recognise, or not."""
    agent = user_agent or ""
    browser = next((name for token, name in _BROWSERS if token in agent), None)
    system = next((name for token, name in _SYSTEMS if token in agent), None)
    if browser and system:
        return f"{browser} on {system}"
    return browser or system or "an unrecognised device or app"


async def is_new_device(session: AsyncSession, user_id: UUID, user_agent: str | None) -> bool:
    """Whether this account has signed in before, but never from this
    device. Must be asked before the new session is created. A first
    ever sign-in is not "new": there is nothing to compare it with, and
    nobody to surprise."""
    result = await session.execute(
        select(Session.user_agent).where(Session.user_id == user_id).distinct()
    )
    known = {device_signature(agent) for agent in result.scalars().all()}
    return bool(known) and device_signature(user_agent) not in known
