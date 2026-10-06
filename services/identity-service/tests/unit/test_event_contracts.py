"""Producer side of contracts/events for identity-service: every account
event is built through the same helper the real code paths use
(app/services/outbox.py) and serialized as the relay puts it on the
wire, then validated against its committed JSON Schema.
"""

import uuid

import pytest
from fincore_common import EventEnvelope, EventType

from app.domain.outbox import OutboxEvent
from app.domain.user import User, UserStatus
from app.services.outbox import STATUS_EVENTS, user_outbox_event
from tests.contracts import assert_valid_event


def _on_the_wire(row: OutboxEvent) -> dict:
    envelope = EventEnvelope(
        event_id=uuid.uuid4(),
        event_type=EventType(row.event_type),
        producer="identity-service",
        correlation_id=row.correlation_id,
        data=row.payload,
    )
    return envelope.model_dump(mode="json")


def _user(status: UserStatus = UserStatus.ACTIVE) -> User:
    return User(
        id=uuid.uuid4(),
        email="ada@example.com",
        phone="+998901112233",
        password_hash="x",
        first_name="Ada",
        last_name="Lovelace",
        status=status,
    )


def test_user_registered_matches_its_contract() -> None:
    user = _user()
    row = user_outbox_event(user, EventType.USER_REGISTERED, actor_user_id=user.id)
    assert_valid_event(_on_the_wire(row))


@pytest.mark.parametrize(
    ("previous", "new"),
    [
        (UserStatus.ACTIVE, UserStatus.BLOCKED),
        (UserStatus.ACTIVE, UserStatus.SUSPENDED),
        (UserStatus.BLOCKED, UserStatus.ACTIVE),
    ],
)
def test_status_change_events_match_their_contracts(
    previous: UserStatus, new: UserStatus
) -> None:
    row = user_outbox_event(
        _user(new), STATUS_EVENTS[new], actor_user_id=uuid.uuid4(), previous_status=previous.value
    )
    assert_valid_event(_on_the_wire(row))


@pytest.mark.parametrize("event", [EventType.USER_ROLE_GRANTED, EventType.USER_ROLE_REVOKED])
def test_role_events_match_their_contracts(event: EventType) -> None:
    row = user_outbox_event(_user(), event, actor_user_id=None, role="ADMIN")
    assert_valid_event(_on_the_wire(row))


def test_no_profile_data_goes_on_the_wire() -> None:
    user = _user()
    payload = user_outbox_event(user, EventType.USER_REGISTERED, actor_user_id=user.id).payload
    assert set(payload) == {"user_id", "actor_user_id", "status"}


def test_user_login_matches_its_contract() -> None:
    user = _user()
    row = user_outbox_event(
        user,
        EventType.USER_LOGIN,
        actor_user_id=user.id,
        session_id=str(uuid.uuid4()),
        ip_address="203.0.113.7",
        user_agent="Firefox",
    )
    assert_valid_event(_on_the_wire(row))


def test_user_password_changed_matches_its_contract() -> None:
    user = _user()
    row = user_outbox_event(
        user, EventType.USER_PASSWORD_CHANGED, actor_user_id=user.id, sessions_revoked=2
    )
    assert_valid_event(_on_the_wire(row))
    assert "password" not in str(row.payload).replace("password_changed", "")


def test_profile_updated_names_fields_but_never_their_values() -> None:
    user = _user()
    row = user_outbox_event(
        user, EventType.USER_PROFILE_UPDATED, actor_user_id=user.id, changed_fields="email,phone"
    )

    wire = _on_the_wire(row)

    assert_valid_event(wire)
    assert user.email not in str(wire) and user.phone not in str(wire)
