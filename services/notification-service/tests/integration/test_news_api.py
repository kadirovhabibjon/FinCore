"""News in the bell: fetched from feeds, the same for everyone, unread
per customer since they last looked."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.config import settings
from app.db import session as db_session
from app.domain.news import NewsItem, NewsRead
from app.main import app
from app.services import news

pytestmark = pytest.mark.usefixtures("migrated_database")


def _rss(*items: tuple[str, str, str], first_hour: int = 1) -> bytes:
    body = "".join(
        f"<item><title>{title}</title><description>{summary}</description>"
        f"<link>{link}</link><pubDate>Mon, 5 Oct 2026 0{index}:00:00 GMT</pubDate></item>"
        for index, (title, summary, link) in enumerate(items, start=first_hour)
    )
    return f"<rss><channel>{body}</channel></rss>".encode()


_CBU = _rss(
    ("Markaziy bank asosiy stavkani saqlab qoldi", "", "https://cbu.uz/n/1"), first_hour=0
)
_SPOT = _rss(
    ("Ipoteka kreditlari arzonlashdi", "Banklar foizlarni tushirdi.", "https://www.spot.uz/a"),
    ("Germaniyada shamol turbinasi qurildi", "Balandligi 365 metr.", "https://www.spot.uz/b"),
)


@pytest.fixture(autouse=True)
async def _feeds(monkeypatch: pytest.MonkeyPatch, migrated_database: None) -> None:
    def serve(request: httpx.Request) -> httpx.Response:
        if request.url.host == "cbu.uz":
            return httpx.Response(200, content=_CBU)
        if request.url.host == "www.spot.uz":
            return httpx.Response(200, content=_SPOT)
        if request.url.host == "down.example":
            raise httpx.ConnectError("down", request=request)
        return httpx.Response(200, content=b"<html>not a feed</html>")

    monkeypatch.setattr(news, "transport", httpx.MockTransport(serve))
    monkeypatch.setattr(
        settings, "news_feeds", "https://down.example/rss, https://cbu.uz/rss, https://bad.example/"
    )
    monkeypatch.setattr(settings, "news_filtered_feeds", "https://www.spot.uz/oz/rss/")
    async with db_session.async_session_factory() as session:
        await session.execute(delete(NewsItem))
        await session.execute(delete(NewsRead))
        await session.commit()


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _news(client: AsyncClient, token: str) -> dict:
    response = await client.get("/api/v1/news", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    return response.json()


async def test_a_refresh_keeps_relevant_articles_once_and_survives_broken_feeds() -> None:
    assert await news.refresh() == 2
    assert await news.refresh() == 0  # the same feeds again: nothing new

    async with db_session.async_session_factory() as session:
        stored = (await session.execute(select(NewsItem))).scalars().all()
    assert {(item.source, item.title) for item in stored} == {
        ("cbu.uz", "Markaziy bank asosiy stavkani saqlab qoldi"),
        # The general business feed is filtered: the wind turbine is not banking news.
        ("spot.uz", "Ipoteka kreditlari arzonlashdi"),
    }


async def test_news_is_unread_until_the_customer_opens_it(
    issue: Callable[[uuid.UUID], str],
) -> None:
    await news.refresh()
    me, someone_else = issue(uuid.uuid4()), issue(uuid.uuid4())

    async with _client() as client:
        before = await _news(client, me)
        read = await client.post("/api/v1/news/read", headers={"Authorization": f"Bearer {me}"})
        after = await _news(client, me)
        theirs = await _news(client, someone_else)
        one = await client.get(
            f"/api/v1/news/{before['items'][0]['id']}", headers={"Authorization": f"Bearer {me}"}
        )

    assert before["unread_count"] == 2
    # Newest first, with everything needed to show it and to open the original.
    assert before["items"][0] == {
        "id": before["items"][0]["id"],
        "title": "Ipoteka kreditlari arzonlashdi",
        "summary": "Banklar foizlarni tushirdi.",
        "source": "spot.uz",
        "url": "https://www.spot.uz/a",
        "published_at": "2026-10-05T01:00:00Z",
        "unread": True,
    }
    assert read.status_code == 204
    assert after["unread_count"] == 0
    assert [item["unread"] for item in after["items"]] == [False, False]
    assert theirs["unread_count"] == 2  # reading is per customer
    assert one.status_code == 200 and one.json()["title"] == "Ipoteka kreditlari arzonlashdi"


async def test_a_first_time_visitor_is_not_shown_an_old_backlog_as_unread(
    issue: Callable[[uuid.UUID], str],
) -> None:
    await news.refresh()
    async with db_session.async_session_factory() as session:
        items = (await session.execute(select(NewsItem))).scalars().all()
        for item in items:
            item.fetched_at = datetime.now(UTC) - timedelta(days=3)
        await session.commit()

    async with _client() as client:
        listing = await _news(client, issue(uuid.uuid4()))

    assert listing["unread_count"] == 0
    assert len(listing["items"]) == 2


async def test_only_the_newest_articles_are_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "news_max_items", 1)

    await news.refresh()

    async with db_session.async_session_factory() as session:
        stored = (await session.execute(select(NewsItem))).scalars().all()
    assert [item.title for item in stored] == ["Ipoteka kreditlari arzonlashdi"]


async def test_needs_a_signed_in_customer_and_a_real_article(
    issue: Callable[[uuid.UUID], str],
) -> None:
    async with _client() as client:
        assert (await client.get("/api/v1/news")).status_code == 401
        assert (await client.post("/api/v1/news/read")).status_code == 401
        missing = await client.get(
            f"/api/v1/news/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {issue(uuid.uuid4())}"},
        )
    assert missing.status_code == 404
