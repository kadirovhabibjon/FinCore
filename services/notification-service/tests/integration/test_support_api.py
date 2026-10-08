"""Writing to FinCore's staff, and staff answering."""

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, update

from app.db import session as db_session
from app.domain.support import SupportMessage, SupportThread
from app.main import app

pytestmark = pytest.mark.usefixtures("migrated_database")

Issue = Callable[..., str]


@pytest.fixture(autouse=True)
async def _clean(migrated_database: None) -> None:
    async with db_session.async_session_factory() as session:
        await session.execute(delete(SupportMessage))
        await session.execute(delete(SupportThread))
        await session.commit()


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _auth(issue: Issue, user_id: uuid.UUID, *roles: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue(user_id, list(roles))}"}


async def _write(client: AsyncClient, headers: dict[str, str], body: str) -> dict:
    response = await client.post("/api/v1/support/messages", json={"body": body}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def test_a_conversation_is_empty_until_the_customer_writes(issue: Issue) -> None:
    async with _client() as client:
        mine = await client.get(
            "/api/v1/support/messages", headers=_auth(issue, uuid.uuid4())
        )
        anonymous = await client.get("/api/v1/support/messages")

    assert anonymous.status_code == 401
    assert mine.status_code == 200
    assert mine.json() == {"status": "OPEN", "unread_count": 0, "items": []}


async def test_a_customer_and_staff_talk_and_each_is_told_about_the_other(issue: Issue) -> None:
    customer_id = uuid.uuid4()
    customer = _auth(issue, customer_id)
    staff = _auth(issue, uuid.uuid4(), "SUPPORT")

    async with _client() as client:
        first = await _write(client, customer, "  My transfer is stuck.  ")
        inbox = (await client.get("/api/v1/admin/support/threads", headers=staff)).json()
        opened = await client.post(
            f"/api/v1/admin/support/threads/{customer_id}/read", headers=staff
        )
        answer = await client.post(
            f"/api/v1/admin/support/threads/{customer_id}/messages",
            json={"body": "We are looking into it."},
            headers=staff,
        )
        mine = (await client.get("/api/v1/support/messages", headers=customer)).json()
        bell = (await client.get("/api/v1/notifications", headers=customer)).json()
        read = await client.post("/api/v1/support/read", headers=customer)
        after = (await client.get("/api/v1/support/messages", headers=customer)).json()
        inbox_after = (await client.get("/api/v1/admin/support/threads", headers=staff)).json()
        detail = (
            await client.get(f"/api/v1/admin/support/threads/{customer_id}", headers=staff)
        ).json()

    assert first["sender"] == "CUSTOMER" and first["body"] == "My transfer is stuck."
    assert inbox["waiting_count"] == 1
    assert inbox["unread_count"] == 1
    assert len(inbox["items"]) == 1
    assert inbox["items"][0] | {"last_message_at": None} == {
        "user_id": str(customer_id),
        "status": "OPEN",
        "last_message_at": None,
        "last_sender": "CUSTOMER",
        "last_body": "My transfer is stuck.",
        "unread_count": 1,
    }
    assert opened.status_code == 200 and opened.json()["unread_count"] == 0
    assert answer.status_code == 201
    # The customer never learns which staff member answered.
    assert set(answer.json()) == {"id", "sender", "body", "created_at"}

    assert mine["unread_count"] == 1
    assert [(m["sender"], m["body"]) for m in mine["items"]] == [
        ("CUSTOMER", "My transfer is stuck."),
        ("STAFF", "We are looking into it."),
    ]
    told = [item for item in bell["items"] if item["type"] == "support.reply"]
    assert len(told) == 1
    assert (told[0]["title"], told[0]["body"]) == ("Support replied", "We are looking into it.")
    assert told[0]["read"] is False

    assert read.status_code == 204
    assert after["unread_count"] == 0
    # Answered: nobody is waiting, though the conversation stays open.
    assert inbox_after["waiting_count"] == 0
    assert inbox_after["unread_count"] == 0
    assert inbox_after["items"][0]["last_sender"] == "STAFF"
    assert [m["sender"] for m in detail["items"]] == ["CUSTOMER", "STAFF"]


async def test_a_resolved_conversation_reopens_when_the_customer_writes_again(issue: Issue) -> None:
    customer_id = uuid.uuid4()
    customer = _auth(issue, customer_id)
    staff = _auth(issue, uuid.uuid4(), "ADMIN")

    async with _client() as client:
        await _write(client, customer, "Hello")
        resolved = await client.post(
            f"/api/v1/admin/support/threads/{customer_id}/resolve", headers=staff
        )
        open_only = (
            await client.get(
                "/api/v1/admin/support/threads", params={"status": "OPEN"}, headers=staff
            )
        ).json()
        seen_by_customer = (await client.get("/api/v1/support/messages", headers=customer)).json()
        await _write(client, customer, "One more thing")
        again = (await client.get("/api/v1/admin/support/threads", headers=staff)).json()
        reopened = await client.post(
            f"/api/v1/admin/support/threads/{customer_id}/reopen", headers=staff
        )

    assert resolved.json()["status"] == "RESOLVED" and resolved.json()["unread_count"] == 0
    assert open_only == {"waiting_count": 0, "unread_count": 0, "items": []}
    assert seen_by_customer["status"] == "RESOLVED"
    assert again["waiting_count"] == 1
    assert (again["items"][0]["status"], again["items"][0]["unread_count"]) == ("OPEN", 1)
    assert reopened.status_code == 200


async def test_the_inbox_shows_open_conversations_first_then_the_latest(issue: Issue) -> None:
    staff = _auth(issue, uuid.uuid4(), "SUPPORT")
    old, resolved, new = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    async with _client() as client:
        for user_id in (old, resolved, new):
            await _write(client, _auth(issue, user_id), f"from {user_id}")
        await client.post(f"/api/v1/admin/support/threads/{resolved}/resolve", headers=staff)
        async with db_session.async_session_factory() as session:
            await session.execute(
                update(SupportThread)
                .where(SupportThread.user_id == old)
                .values(last_message_at=datetime.now(UTC) - timedelta(days=2))
            )
            # Resolved last, but resolved conversations come after open ones.
            await session.execute(
                update(SupportThread)
                .where(SupportThread.user_id == resolved)
                .values(last_message_at=datetime.now(UTC) + timedelta(minutes=1))
            )
            await session.commit()
        inbox = (await client.get("/api/v1/admin/support/threads", headers=staff)).json()
        page = (
            await client.get(
                "/api/v1/admin/support/threads", params={"limit": 1, "offset": 1}, headers=staff
            )
        ).json()

    assert [item["user_id"] for item in inbox["items"]] == [str(new), str(old), str(resolved)]
    assert inbox["waiting_count"] == 2
    # Every unopened message, whichever page of the inbox is shown.
    assert inbox["unread_count"] == page["unread_count"] == 2
    assert [item["user_id"] for item in page["items"]] == [str(old)]


async def test_a_customer_sees_only_their_own_conversation(issue: Issue) -> None:
    mine, theirs = _auth(issue, uuid.uuid4()), _auth(issue, uuid.uuid4())

    async with _client() as client:
        await _write(client, mine, "mine")
        await _write(client, theirs, "theirs")
        seen = (await client.get("/api/v1/support/messages", headers=mine)).json()

    assert [message["body"] for message in seen["items"]] == ["mine"]


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", "/api/v1/admin/support/threads", None),
        ("get", "/api/v1/admin/support/threads/{user_id}", None),
        ("post", "/api/v1/admin/support/threads/{user_id}/read", None),
        ("post", "/api/v1/admin/support/threads/{user_id}/messages", {"body": "hi"}),
        ("post", "/api/v1/admin/support/threads/{user_id}/resolve", None),
        ("post", "/api/v1/admin/support/threads/{user_id}/reopen", None),
    ],
)
async def test_the_staff_side_is_for_staff(
    issue: Issue, method: str, path: str, body: dict | None
) -> None:
    customer_id = uuid.uuid4()
    customer = _auth(issue, customer_id)
    url = path.format(user_id=customer_id)

    async with _client() as client:
        await _write(client, customer, "hello")
        as_customer = await client.request(method, url, json=body, headers=customer)
        anonymous = await client.request(method, url, json=body)
        as_support = await client.request(
            method, url, json=body, headers=_auth(issue, uuid.uuid4(), "SUPPORT")
        )

    assert as_customer.status_code == 403
    assert as_customer.json()["title"] == "Insufficient Role"
    assert anonymous.status_code == 401
    assert as_support.status_code in (200, 201)


async def test_staff_cannot_write_to_someone_who_never_wrote(issue: Issue) -> None:
    staff = _auth(issue, uuid.uuid4(), "SUPPORT")
    nobody = uuid.uuid4()

    async with _client() as client:
        reply = await client.post(
            f"/api/v1/admin/support/threads/{nobody}/messages",
            json={"body": "Hello?"},
            headers=staff,
        )
        detail = await client.get(f"/api/v1/admin/support/threads/{nobody}", headers=staff)
        bell = (
            await client.get("/api/v1/notifications", headers=_auth(issue, nobody))
        ).json()

    assert reply.status_code == detail.status_code == 404
    assert reply.json()["title"] == "Support Thread Not Found"
    assert [item for item in bell["items"] if item["type"] == "support.reply"] == []


@pytest.mark.parametrize("body", ["", "   ", "x" * 2001])
async def test_a_message_must_say_something_and_not_too_much(issue: Issue, body: str) -> None:
    async with _client() as client:
        response = await client.post(
            "/api/v1/support/messages", json={"body": body}, headers=_auth(issue, uuid.uuid4())
        )

    assert response.status_code == 422


async def test_a_long_message_is_kept_whole_and_previewed_short(issue: Issue) -> None:
    customer_id = uuid.uuid4()
    long_text = "word " * 399 + "end"  # 1998 characters

    async with _client() as client:
        sent = await _write(client, _auth(issue, customer_id), long_text)
        inbox = (
            await client.get(
                "/api/v1/admin/support/threads", headers=_auth(issue, uuid.uuid4(), "SUPPORT")
            )
        ).json()

    assert sent["body"] == long_text
    preview = inbox["items"][0]["last_body"]
    assert len(preview) == 200 and preview.endswith("…") and long_text.startswith(preview[:-1])


async def test_first_messages_sent_at_once_all_arrive_and_are_all_counted(issue: Issue) -> None:
    customer_id = uuid.uuid4()
    customer = _auth(issue, customer_id)

    async with _client() as client:
        responses = await asyncio.gather(
            *(
                client.post(
                    "/api/v1/support/messages", json={"body": f"message {n}"}, headers=customer
                )
                for n in range(8)
            )
        )
        inbox = (
            await client.get(
                "/api/v1/admin/support/threads", headers=_auth(issue, uuid.uuid4(), "SUPPORT")
            )
        ).json()
        mine = (await client.get("/api/v1/support/messages", headers=customer)).json()

    assert [response.status_code for response in responses] == [201] * 8
    assert len(inbox["items"]) == 1
    assert inbox["items"][0]["unread_count"] == 8
    assert sorted(message["body"] for message in mine["items"]) == [
        f"message {n}" for n in range(8)
    ]


async def test_a_customer_cannot_flood_the_inbox(issue: Issue) -> None:
    customer_id = uuid.uuid4()
    customer = _auth(issue, customer_id)

    async with _client() as client:
        for n in range(20):
            await _write(client, customer, f"message {n}")
        refused = await client.post(
            "/api/v1/support/messages", json={"body": "one too many"}, headers=customer
        )
        # Ten minutes on, the oldest no longer count.
        async with db_session.async_session_factory() as session:
            await session.execute(
                update(SupportMessage)
                .where(SupportMessage.user_id == customer_id)
                .values(created_at=datetime.now(UTC) - timedelta(minutes=11))
            )
            await session.commit()
        later = await client.post(
            "/api/v1/support/messages", json={"body": "later"}, headers=customer
        )
        other = await client.post(
            "/api/v1/support/messages",
            json={"body": "someone else is not affected"},
            headers=_auth(issue, uuid.uuid4()),
        )

    assert refused.status_code == 429 and refused.json()["title"] == "Too Many Messages"
    assert later.status_code == 201 and other.status_code == 201
