from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DeadLetterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_id: UUID
    topic: str
    last_error: str
    attempts: int
    created_at: datetime
    replayed_at: datetime | None
