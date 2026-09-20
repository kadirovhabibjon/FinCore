from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.fraud_check import FraudDecision


class RiskCheckRequest(BaseModel):
    user_id: UUID
    amount_minor: int = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    operation_type: str = Field(min_length=1, max_length=64)
    operation_id: UUID


class RiskCheckResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    decision: FraudDecision
    score: int
    rules_triggered: list[str]
    created_at: datetime
