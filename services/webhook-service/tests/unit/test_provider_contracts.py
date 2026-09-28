"""Consumer side of contracts/openapi: webhook-service's MerchantClient
against payment-service's committed contract for
`GET /internal/v1/merchants/{merchant_id}` (see tests/contracts.py's
ContractFake) — the request must be one payment-service accepts, and the
client must correctly read a response shaped exactly as documented.
"""

import uuid

from app.services.merchants import MerchantClient, MerchantLookupOutcome
from tests.contracts import ContractFake


async def test_merchant_lookup_speaks_payment_services_contract() -> None:
    merchant_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    fake = ContractFake(
        provider="payment-service",
        responses={
            ("GET", "/internal/v1/merchants/{merchant_id}"): (
                200,
                {"id": str(merchant_id), "owner_user_id": str(owner_id), "status": "ACTIVE"},
            )
        },
    )
    client = MerchantClient(
        base_url="http://payment",
        internal_token="test-only-internal-token",
        timeout_seconds=2.0,
        transport=fake.transport(),
    )

    result = await client.get_merchant(merchant_id)

    assert result.outcome is MerchantLookupOutcome.FOUND
    assert result.merchant is not None
    assert result.merchant.owner_user_id == owner_id
    assert result.merchant.status == "ACTIVE"
    assert fake.calls == [("GET", "/internal/v1/merchants/{merchant_id}")]
