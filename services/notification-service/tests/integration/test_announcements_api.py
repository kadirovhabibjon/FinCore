"""Announcements: an ADMIN writes once, every customer finds it in
their bell among their own notifications."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fincore_common import EventEnvelope, EventType
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, update

from app.db import session as db_session
from app.domain.announcement import Announcement, AnnouncementRead
from app.main import app
from app.services.consumer import handle_event

pytestmark = pytest.mark.usefixtures("migrated_database")

Issue = Callable[..., str]


@pytest.fixture(autouse=True)
async def _clean(migrated_database: None) -> None:
    async with db_session.async_session_factory() as session:
        await session.execute(delete(Announcement))
        await session.execute(delete(AnnouncementRead))
        await session.commit()


@pytest.fixture
def staff(issue: Issue) -> Callable[..., dict[str, str]]:
    """Headers for a staff member holding the given roles."""

    def _headers(*roles: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {issue(uuid.uuid4(), list(roles))}"}

    return _headers


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _customer(issue: Issue) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue(uuid.uuid4())}"}


async def _publish(
    client: AsyncClient, headers: dict[str, str], title: str = "Maintenance"
) -> dict:
    response = await client.post(
        "/api/v1/admin/announcements",
        json={"title": f"  {title} ", "body": "FinCore will be unavailable on Sunday 02:00-03:00."},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_an_admins_announcement_reaches_every_customers_bell(
    issue: Issue,
    staff: Callable[..., dict[str, str]],
) -> None:
    first, second = _customer(issue), _customer(issue)
    async with _client() as client:
        published = await _publish(client, staff("ADMIN"))
        mine = (await client.get("/api/v1/notifications", headers=first)).json()
        theirs = (await client.get("/api/v1/notifications", headers=second)).json()

        await client.post("/api/v1/notifications/read", headers=first)
        mine_after = (await client.get("/api/v1/notifications", headers=first)).json()
        theirs_after = (await client.get("/api/v1/notifications", headers=second)).json()

    assert published["title"] == "Maintenance"  # trimmed
    for listing in (mine, theirs):
        assert listing["unread_count"] == 1
        assert listing["items"] == [
            {
                "id": published["id"],
                "type": "announcement",
                "title": "Maintenance",
                "body": "FinCore will be unavailable on Sunday 02:00-03:00.",
                "params": None,
                "created_at": published["created_at"],
                "read": False,
            }
        ]
    # Reading is per customer.
    assert mine_after["unread_count"] == 0 and mine_after["items"][0]["read"] is True
    assert theirs_after["unread_count"] == 1


async def test_announcements_sit_among_the_customers_own_notifications_by_time(
    issue: Issue,
    staff: Callable[..., dict[str, str]],
) -> None:
    me = uuid.uuid4()
    headers = {"Authorization": f"Bearer {issue(me)}"}
    async with _client() as client:
        await _publish(client, staff("ADMIN"), "Older news")
        async with db_session.async_session_factory() as session:
            await session.execute(
                update(Announcement).values(created_at=datetime.now(UTC) - timedelta(hours=1))
            )
            await session.commit()
        await handle_event(
            EventEnvelope(
                event_type=EventType.TRANSFER_COMPLETED,
                producer="payment-service",
                data={
                    "transfer_id": str(uuid.uuid4()),
                    "reference": "TRF-MIX",
                    "initiator_user_id": str(me),
                    "amount_minor": 100,
                    "currency": "UZS",
                    "status": "COMPLETED",
                    "failure_reason": None,
                    "completed_at": "2026-01-01T00:00:00Z",
                },
            ),
            [],
        )
        await _publish(client, staff("ADMIN"), "Newest")

        listing = (await client.get("/api/v1/notifications", headers=headers)).json()
        page = (
            await client.get(
                "/api/v1/notifications", params={"limit": 1, "offset": 1}, headers=headers
            )
        ).json()

    assert [item["title"] for item in listing["items"]] == [
        "Newest",
        "Transfer completed",
        "Older news",
    ]
    assert listing["unread_count"] == 3
    assert [item["title"] for item in page["items"]] == ["Transfer completed"]


async def test_someone_new_is_not_shown_old_announcements_as_unread(
    issue: Issue,
    staff: Callable[..., dict[str, str]],
) -> None:
    async with _client() as client:
        await _publish(client, staff("ADMIN"))
        async with db_session.async_session_factory() as session:
            await session.execute(
                update(Announcement).values(created_at=datetime.now(UTC) - timedelta(days=30))
            )
            await session.commit()
        listing = (await client.get("/api/v1/notifications", headers=_customer(issue))).json()

    assert listing["unread_count"] == 0
    assert [item["read"] for item in listing["items"]] == [True]


async def test_a_withdrawn_announcement_disappears_for_everyone(
    issue: Issue,
    staff: Callable[..., dict[str, str]],
) -> None:
    admin = staff("ADMIN")
    async with _client() as client:
        published = await _publish(client, admin)
        gone = await client.delete(f"/api/v1/admin/announcements/{published['id']}", headers=admin)
        again = await client.delete(f"/api/v1/admin/announcements/{published['id']}", headers=admin)
        listing = (await client.get("/api/v1/notifications", headers=_customer(issue))).json()
        for_staff = await client.get("/api/v1/admin/announcements", headers=admin)

    assert gone.status_code == 204 and again.status_code == 404
    assert listing == {"unread_count": 0, "items": []}
    assert for_staff.json() == []


async def test_only_admins_publish_and_only_staff_see_the_admin_list(
    issue: Issue,
    staff: Callable[..., dict[str, str]],
) -> None:
    body = {"title": "Hello", "body": "World"}
    async with _client() as client:
        published = await _publish(client, staff("ADMIN"))
        anonymous = await client.post("/api/v1/admin/announcements", json=body)
        customer = await client.post(
            "/api/v1/admin/announcements", json=body, headers=_customer(issue)
        )
        support_writes = await client.post(
            "/api/v1/admin/announcements", json=body, headers=staff("SUPPORT")
        )
        support_reads = await client.get("/api/v1/admin/announcements", headers=staff("SUPPORT"))
        customer_reads = await client.get("/api/v1/admin/announcements", headers=_customer(issue))
        support_deletes = await client.delete(
            f"/api/v1/admin/announcements/{published['id']}", headers=staff("SUPPORT")
        )
        blank = await client.post(
            "/api/v1/admin/announcements",
            json={"title": "   ", "body": "x"},
            headers=staff("ADMIN"),
        )
        too_long = await client.post(
            "/api/v1/admin/announcements",
            json={"title": "x" * 121, "body": "x"},
            headers=staff("ADMIN"),
        )

    assert anonymous.status_code == 401
    assert customer.status_code == support_writes.status_code == 403
    assert support_reads.status_code == 200 and len(support_reads.json()) == 1
    assert customer_reads.status_code == 403
    assert support_deletes.status_code == 403
    assert blank.status_code == too_long.status_code == 422
