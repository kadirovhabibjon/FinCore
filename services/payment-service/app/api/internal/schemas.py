from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.merchant import MerchantStatus


class MerchantOwnershipResponse(BaseModel):
    """Lets a caller (webhook-service, registering a webhook endpoint)
    verify who owns a merchant and whether it's active, without needing
    its own copy of the merchants table — same reasoning as
    ledger-service's SystemAccountResponse.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_user_id: UUID
    status: MerchantStatus
