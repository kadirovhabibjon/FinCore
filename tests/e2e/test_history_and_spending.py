"""The history narrowed, and spending split by category, through the
real gateway and services."""

from e2e_client import FinCoreClient, User, idempotency_key


def test_history_is_filtered_and_spending_is_split_by_category(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    mine = api.funded_wallet(user, 10_000_000)
    theirs = api.funded_wallet(other_user, 100_000)
    sent = api.transfer(user, source=mine, destination=theirs, amount="250.00").json()
    received = api.transfer(other_user, source=theirs, destination=mine, amount="40.00").json()
    topped_up = api.gateway.post(
        "/api/v1/services/beeline/payments",
        json={"source_wallet_id": mine, "account": "901234567", "amount": "25000"},
        headers={**user.auth, **idempotency_key()},
    ).json()
    assert topped_up["status"] == "SUCCESS"

    def listed(**params: str) -> list[str]:
        response = api.gateway.get("/api/v1/transactions", params=params, headers=user.auth)
        assert response.status_code == 200, response.text
        return [item["reference"] for item in response.json()]

    assert set(listed()) == {sent["reference"], received["reference"], topped_up["reference"]}
    assert listed(direction="IN") == [received["reference"]]
    assert listed(type="TRANSFER", direction="OUT") == [sent["reference"]]
    assert listed(type="PAYMENT") == [topped_up["reference"]]
    assert listed(q="beeline") == [topped_up["reference"]]
    assert listed(q="901234567") == [topped_up["reference"]]
    assert listed(q="no such thing") == []
    assert listed(date_from="2999-01-01") == []
    assert api.gateway.get(
        "/api/v1/transactions", params={"direction": "SIDEWAYS"}, headers=user.auth
    ).status_code == 422

    spending = api.gateway.get(
        "/api/v1/transactions/stats/categories", params={"months": 1}, headers=user.auth
    )
    assert spending.status_code == 200
    uzs = next(c for c in spending.json()["currencies"] if c["currency"] == "UZS")
    assert uzs["categories"] == [
        {"category": "MOBILE", "amount_minor": 2_500_000, "count": 1},
        {"category": "TRANSFERS", "amount_minor": 25_000, "count": 1},
    ]
    assert uzs["total_minor"] == 2_525_000
    assert api.gateway.get("/api/v1/transactions/stats/categories").status_code == 401
