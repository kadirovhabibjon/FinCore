from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateWebhookEndpointRequest(BaseModel):
    merchant_id: UUID
    url: str = Field(..., min_length=1, max_length=2048)


class WebhookEndpointResponse(BaseModel):
    """Never includes `secret` — a plain GET/list must not be able to
    read back the signing key, only see that an endpoint exists and
    what state it's in.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    merchant_id: UUID
    url: str
    status: str
    consecutive_failures: int
    created_at: datetime
    updated_at: datetime


class WebhookEndpointWithSecretResponse(WebhookEndpointResponse):
    """Returned only once, at creation and at rotation time (spec
    Section 17: "per-endpoint secrets, stored securely, rotatable") —
    the caller must save it then, since no later call ever returns it
    again.
    """

    secret: str


class WebhookAttemptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    attempt_number: int
    status_code: int | None
    latency_ms: int | None
    error: str | None
    attempted_at: datetime


class WebhookDeliveryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_id: UUID
    event_type: str
    status: str
    attempts: int
    last_error: str | None
    created_at: datetime
    attempt_history: list[WebhookAttemptResponse] = []
