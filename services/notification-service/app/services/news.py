"""Banking news for the bell: read from public RSS feeds, kept as the
feed gives it (headline, summary, link), shown with its source.

Everything in a feed is someone else's text. It is parsed with a
hardened XML parser, reduced to plain text (no markup survives), cut to
length, and its link is only kept if it is an ordinary web address - the
web app renders the text as text and opens the link in a new tab.
"""

import asyncio
import html
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import httpx
from defusedxml import ElementTree
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db import session as db_session
from app.domain.news import NewsItem

logger = logging.getLogger(__name__)

# Tests swap in an httpx.MockTransport.
transport: httpx.AsyncBaseTransport | None = None

_MAX_FEED_BYTES = 2_000_000
_TAG = re.compile(r"<[^>]*>")
_SPACE = re.compile(r"\s+")
_USER_AGENT = "FinCore-news/1.0 (RSS reader)"


@dataclass(frozen=True)
class Article:
    source: str
    guid: str
    title: str
    summary: str
    url: str
    published_at: datetime


def _text(value: str | None, limit: int) -> str:
    """Feed markup as plain text: entities decoded (feeds double-encode
    often enough to do it twice), tags dropped, whitespace collapsed."""
    if not value:
        return ""
    plain = _TAG.sub(" ", html.unescape(html.unescape(value)))
    plain = _SPACE.sub(" ", plain).strip()
    return plain if len(plain) <= limit else plain[: limit - 1].rstrip() + "…"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _published(value: str | None) -> datetime:
    try:
        parsed = parsedate_to_datetime(value or "")
    except (TypeError, ValueError):
        return datetime.now(UTC)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    # A feed's clock can be ahead; nothing is published in the future.
    return min(parsed, datetime.now(UTC))


def _web_url(value: str) -> str | None:
    parts = urlsplit(value.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    return value.strip()[:1000]


def parse_feed(content: bytes, *, source: str) -> list[Article]:
    """The articles in an RSS 2.0 document. Namespaces are ignored (some
    feeds put a default one on <rss>); an item without a headline or a
    usable link is skipped. Raises ValueError if it isn't XML at all."""
    try:
        root = ElementTree.fromstring(content)
    except Exception as exc:  # malformed, or refused by defusedxml
        raise ValueError(f"not a readable feed: {type(exc).__name__}") from exc

    articles: list[Article] = []
    for element in root.iter():
        if _local(element.tag) != "item":
            continue
        fields = {_local(child.tag): (child.text or "") for child in element}
        title = _text(fields.get("title"), 300)
        url = _web_url(fields.get("link", ""))
        if not title or url is None:
            continue
        articles.append(
            Article(
                source=source,
                guid=(fields.get("guid") or url).strip()[:500],
                title=title,
                summary=_text(fields.get("description"), 2000),
                url=url,
                published_at=_published(fields.get("pubDate")),
            )
        )
    return articles


# Uzbek is written with whichever apostrophe the keyboard offers
# (o'zbek, o‘zbek, oʻzbek): compared as one.
_APOSTROPHES = str.maketrans({"‘": "'", "’": "'", "ʻ": "'", "ʼ": "'", "`": "'"})


def _fold(text: str) -> str:
    return text.translate(_APOSTROPHES).casefold()


def _keywords() -> re.Pattern[str] | None:
    """The configured keywords as one pattern: each a whole word, or the
    start of one when written with a trailing *."""
    parts = []
    for raw in settings.news_keywords.split(","):
        word = _fold(raw.strip())
        if not word.strip("*"):
            continue
        prefix = word.endswith("*")
        parts.append(re.escape(word.rstrip("*")) + (r"[\w']*" if prefix else ""))
    if not parts:
        return None
    return re.compile(r"(?<![\w'])(?:" + "|".join(parts) + r")(?![\w'])")


def is_relevant(article: Article, keywords: re.Pattern[str] | None) -> bool:
    if keywords is None:
        return False
    return keywords.search(_fold(f"{article.title} {article.summary}")) is not None


def _feeds(value: str) -> list[str]:
    return [url.strip() for url in value.split(",") if url.strip()]


async def _fetch(client: httpx.AsyncClient, url: str) -> list[Article]:
    source = (urlsplit(url).hostname or url).removeprefix("www.")
    async with client.stream("GET", url) as response:
        response.raise_for_status()
        content = b""
        async for chunk in response.aiter_bytes():
            content += chunk
            if len(content) > _MAX_FEED_BYTES:
                raise ValueError("feed is too large")
    return parse_feed(content, source=source)


async def collect() -> list[Article]:
    """Every configured feed's articles, relevant ones only. A feed that
    can't be fetched or read is logged and skipped: one broken source
    must not stop the others."""
    keywords = _keywords()
    plan = [(url, False) for url in _feeds(settings.news_feeds)] + [
        (url, True) for url in _feeds(settings.news_filtered_feeds)
    ]
    articles: list[Article] = []
    async with httpx.AsyncClient(
        timeout=settings.news_fetch_timeout_seconds,
        follow_redirects=True,
        headers={"User-Agent": _USER_AGENT},
        transport=transport,
    ) as client:
        for url, filtered in plan:
            try:
                found = await _fetch(client, url)
            except Exception as exc:
                logger.warning("news feed %s skipped: %s", url, exc)
                continue
            articles.extend(a for a in found if not filtered or is_relevant(a, keywords))
    return articles


async def store(session: AsyncSession, articles: list[Article]) -> int:
    """Saves the articles not seen before and returns how many were new;
    then trims the table to the newest `news_max_items`."""
    added = 0
    for article in articles:
        result = await session.execute(
            insert(NewsItem)
            .values(
                source=article.source,
                guid=article.guid,
                title=article.title,
                summary=article.summary,
                url=article.url,
                published_at=article.published_at,
            )
            .on_conflict_do_nothing(constraint="uq_news_items_source_guid")
            .returning(NewsItem.id)
        )
        added += len(result.fetchall())

    keep = (
        select(NewsItem.id)
        .order_by(NewsItem.published_at.desc(), NewsItem.id)
        .limit(settings.news_max_items)
    )
    await session.execute(delete(NewsItem).where(NewsItem.id.not_in(keep)))
    await session.commit()
    return added


async def refresh() -> int:
    articles = await collect()
    async with db_session.async_session_factory() as session:
        added = await store(session, articles)
    if added:
        logger.info("news: %d new article(s)", added)
    return added


async def poll_forever() -> None:
    """Runs for the life of the process (app/main.py). Never raises: a
    failed round is logged and the next one tried on schedule."""
    while True:
        try:
            await refresh()
        except Exception:
            logger.exception("news refresh failed")
        await asyncio.sleep(settings.news_poll_interval_seconds)
