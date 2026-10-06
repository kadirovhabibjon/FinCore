from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EventType(enum.StrEnum):
    """Domain events (spec Section 14.3). A producer only ever emits the
    subset tied to its own aggregate; a consumer subscribes to whichever
    subset it cares about. New event types are added here as the
    services that emit them are built — this list is not aspirational,
    every member here is actually produced by some service.
    """

    # identity-service, on the `users` topic.
    USER_REGISTERED = "user.registered"
    # spec Section 18's USER_LOGIN.
    USER_LOGIN = "user.login"
    USER_BLOCKED = "user.blocked"
    USER_SUSPENDED = "user.suspended"
    USER_REACTIVATED = "user.reactivated"
    USER_ROLE_GRANTED = "user.role_granted"
    USER_ROLE_REVOKED = "user.role_revoked"
    # spec Section 18's PASSWORD_CHANGED.
    USER_PASSWORD_CHANGED = "user.password_changed"
    # The user edited their own name, email or phone.
    USER_PROFILE_UPDATED = "user.profile_updated"

    # fraud-service, on the `fraud` topic.
    FRAUD_DETECTED = "fraud.detected"
    FRAUD_REVIEW_REQUIRED = "fraud.review_required"

    TRANSFER_COMPLETED = "transfer.completed"
    TRANSFER_FAILED = "transfer.failed"
    # A customer asked another for money, or the other declined. Paying
    # a request is an ordinary transfer (transfer.completed).
    MONEY_REQUEST_CREATED = "money_request.created"
    MONEY_REQUEST_DECLINED = "money_request.declined"
    PAYMENT_COMPLETED = "payment.completed"
    PAYMENT_FAILED = "payment.failed"
    PAYMENT_REFUNDED = "payment.refunded"


class EventEnvelope(BaseModel):
    """The wire format every event takes, producer or consumer side
    (spec Section 14.2). `data` is producer-defined per `event_type` —
    fincore-common deliberately doesn't know its shape, the same way
    ledger-service doesn't know *why* a posting happens
    (docs/context-map.md).
    """

    event_id: UUID = Field(default_factory=uuid4)
    event_type: EventType
    event_version: int = 1
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    producer: str
    correlation_id: str | None = None
    data: dict[str, Any]
