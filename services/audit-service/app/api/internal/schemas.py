from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_id: UUID
    actor_id: UUID | None
    actor_role: str | None
    action: str
    resource_type: str
    resource_id: str
    result: str
    ip_address: str | None
    user_agent: str | None
    correlation_id: str | None
    details: dict[str, Any]
    occurred_at: datetime
    created_at: datetime


class DeadLetterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_id: UUID
    topic: str
    last_error: str
    attempts: int
    created_at: datetime
    replayed_at: datetime | None
