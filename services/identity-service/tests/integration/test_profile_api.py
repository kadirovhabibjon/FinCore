"""A customer editing their own name, email address and phone number."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.db import session as db_session
from app.domain.outbox import OutboxEvent
from app.domain.password_reset import PasswordReset
from app.main import app
from app.services import mailer

pytestmark = pytest.mark.usefixtures("migrated_database")

_PASSWORD = "correct-horse-battery"


class Mail:
    def __init__(self) -> None:
        self.notices: list[dict[str, str]] = []
        self.codes: list[str] = []

    async def send_contact_changed(self, *, to: str, first_name: str, what: str) -> None:
        self.notices.append({"to": to, "first_name": first_name, "what": what})

    async def send_reset_code(self, *, to: str, first_name: str, code: str) -> None:
        self.codes.append(code)


@pytest.fixture
def mail(monkeypatch: pytest.MonkeyPatch) -> Mail:
    outbox = Mail()
    monkeypatch.setattr(settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(mailer, "send_contact_changed", outbox.send_contact_changed)
    monkeypatch.setattr(mailer, "send_reset_code", outbox.send_reset_code)
    return outbox


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _phone() -> str:
    return f"+99890{uuid.uuid4().int % 10**7:07d}"


async def _signed_in(client: AsyncClient) -> dict:
    user = {
        "email": f"{uuid.uuid4().hex[:10]}@example.com",
        "phone": _phone(),
        "password": _PASSWORD,
        "first_name": "Aziza",
        "last_name": "Karimova",
    }
    registered = (await client.post("/api/v1/auth/register", json=user)).json()
    tokens = (
        await client.post(
            "/api/v1/auth/login", json={"email": user["email"], "password": _PASSWORD}
        )
    ).json()
    return {
        **user,
        "id": registered["id"],
        "auth": {"Authorization": f"Bearer {tokens['access_token']}"},
    }


async def _events(user_id: str) -> list[OutboxEvent]:
    async with db_session.async_session_factory() as session:
        result = await session.execute(
            select(OutboxEvent)
            .where(
                OutboxEvent.aggregate_id == user_id,
                OutboxEvent.event_type == "user.profile_updated",
            )
            .order_by(OutboxEvent.created_at)
        )
        return list(result.scalars().all())


async def test_a_name_can_be_changed_without_the_password(mail: Mail) -> None:
    async with _client() as client:
        me = await _signed_in(client)
        response = await client.patch(
            "/api/v1/users/me",
            json={"first_name": "  Aziza-xon ", "last_name": "Karimova"},
            headers=me["auth"],
        )
        again = await client.get("/api/v1/users/me", headers=me["auth"])

    assert response.status_code == 200
    assert response.json()["first_name"] == "Aziza-xon"  # trimmed
    assert response.json()["roles"] == ["USER"]
    assert again.json()["first_name"] == "Aziza-xon"
    # Only what differed is recorded, and no values.
    [event] = await _events(me["id"])
    assert event.payload["changed_fields"] == "first_name"
    assert "Aziza" not in str(event.payload)
    assert mail.notices == []


async def test_a_new_email_and_phone_need_the_current_password(mail: Mail) -> None:
    new_email, new_phone = f"{uuid.uuid4().hex[:10]}@example.com", _phone()
    async with _client() as client:
        me = await _signed_in(client)
        change = {"email": new_email.upper(), "phone": new_phone.replace("+998", "+998 ")}

        missing = await client.patch("/api/v1/users/me", json=change, headers=me["auth"])
        wrong = await client.patch(
            "/api/v1/users/me", json={**change, "current_password": "not-it"}, headers=me["auth"]
        )
        unchanged = await client.get("/api/v1/users/me", headers=me["auth"])
        done = await client.patch(
            "/api/v1/users/me",
            json={**change, "current_password": _PASSWORD},
            headers=me["auth"],
        )

        old_login = await client.post(
            "/api/v1/auth/login", json={"email": me["email"], "password": _PASSWORD}
        )
        new_login = await client.post(
            "/api/v1/auth/login", json={"phone": new_phone, "password": _PASSWORD}
        )

    assert missing.status_code == 422 and missing.json()["title"] == "Current Password Required"
    assert wrong.status_code == 422 and wrong.json()["title"] == "Incorrect Password"
    assert unchanged.json()["email"] == me["email"]
    assert done.status_code == 200
    # Stored the way registration stores them.
    assert (done.json()["email"], done.json()["phone"]) == (new_email, new_phone)
    assert old_login.status_code == 401
    assert new_login.status_code == 200
    [event] = await _events(me["id"])
    assert event.payload["changed_fields"] == "email,phone"
    # The address the account had before is told, so an owner who didn't do it finds out.
    assert mail.notices == [
        {"to": me["email"], "first_name": "Aziza", "what": "email address and phone number"}
    ]


async def test_sending_the_same_values_changes_nothing_and_needs_no_password(mail: Mail) -> None:
    async with _client() as client:
        me = await _signed_in(client)
        response = await client.patch(
            "/api/v1/users/me",
            json={
                "first_name": me["first_name"],
                "last_name": me["last_name"],
                "email": me["email"],
                "phone": me["phone"],
            },
            headers=me["auth"],
        )

    assert response.status_code == 200
    assert await _events(me["id"]) == []
    assert mail.notices == []


async def test_an_email_or_phone_of_another_account_is_refused(mail: Mail) -> None:
    async with _client() as client:
        me, other = await _signed_in(client), await _signed_in(client)

        email = await client.patch(
            "/api/v1/users/me",
            json={"email": other["email"], "current_password": _PASSWORD},
            headers=me["auth"],
        )
        phone = await client.patch(
            "/api/v1/users/me",
            json={"phone": other["phone"], "current_password": _PASSWORD},
            headers=me["auth"],
        )
        mine = await client.get("/api/v1/users/me", headers=me["auth"])

    assert email.status_code == 409 and email.json()["title"] == "Email Already Registered"
    assert phone.status_code == 409 and phone.json()["title"] == "Phone Already Registered"
    assert (mine.json()["email"], mine.json()["phone"]) == (me["email"], me["phone"])
    assert mail.notices == []


async def test_changing_the_email_cancels_a_reset_code_sent_to_the_old_one(mail: Mail) -> None:
    async with _client() as client:
        me = await _signed_in(client)
        await client.post("/api/v1/auth/password-reset/request", json={"email": me["email"]})
        code = mail.codes[-1]
        new_email = f"{uuid.uuid4().hex[:10]}@example.com"
        await client.patch(
            "/api/v1/users/me",
            json={"email": new_email, "current_password": _PASSWORD},
            headers=me["auth"],
        )

        stale = await client.post(
            "/api/v1/auth/password-reset/confirm",
            json={"email": new_email, "code": code, "new_password": "brand-new-password"},
        )

    assert stale.status_code == 422
    async with db_session.async_session_factory() as session:
        resets = (
            (
                await session.execute(
                    select(PasswordReset).where(PasswordReset.user_id == uuid.UUID(me["id"]))
                )
            )
            .scalars()
            .all()
        )
    assert all(reset.used_at is not None for reset in resets)


async def test_input_is_validated_and_the_endpoint_needs_a_session(mail: Mail) -> None:
    async with _client() as client:
        me = await _signed_in(client)
        blank = await client.patch(
            "/api/v1/users/me", json={"first_name": "   "}, headers=me["auth"]
        )
        bad_email = await client.patch(
            "/api/v1/users/me",
            json={"email": "not-an-email", "current_password": _PASSWORD},
            headers=me["auth"],
        )
        bad_phone = await client.patch(
            "/api/v1/users/me",
            json={"phone": "12ab", "current_password": _PASSWORD},
            headers=me["auth"],
        )
        anonymous = await client.patch("/api/v1/users/me", json={"first_name": "X"})

    assert blank.status_code == bad_email.status_code == bad_phone.status_code == 422
    assert anonymous.status_code == 401
