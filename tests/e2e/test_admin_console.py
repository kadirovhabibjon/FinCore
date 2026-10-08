"""What the admin console reads, through the real gateway and the three
services behind it: the dashboard's numbers, one customer's wallets,
and the operations listing with its CSV."""

import csv
import io

from e2e_client import FinCoreClient, User


def test_the_dashboard_counts_what_customers_did(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    staff = api.grant_role(api.register_and_login(), "SUPPORT")
    before = api.gateway.get("/api/v1/admin/stats", params={"days": 1}, headers=staff.auth).json()
    users_before = api.gateway.get("/api/v1/admin/users/stats", headers=staff.auth).json()

    source = api.funded_wallet(user, 100_000)
    destination = api.create_wallet(other_user)
    api.transfer(user, source=source, destination=destination, amount="250.00")
    api.transfer(user, source=source, destination=destination, amount="5000.00")  # no funds
    newcomer = api.register_and_login()

    after = api.gateway.get("/api/v1/admin/stats", params={"days": 1}, headers=staff.auth).json()
    users_after = api.gateway.get("/api/v1/admin/users/stats", headers=staff.auth).json()

    def today(stats: dict) -> dict:
        days = next((c["days"] for c in stats["currencies"] if c["currency"] == "UZS"), None)
        return days[-1] if days else {"transfers": 0, "failed": 0, "volume_minor": 0}

    # Other tests share this stack, so compare with before rather than with zero.
    assert today(after)["transfers"] - today(before)["transfers"] >= 2
    assert today(after)["failed"] - today(before)["failed"] >= 1
    assert today(after)["volume_minor"] - today(before)["volume_minor"] >= 25_000
    assert users_after["total"] - users_before["total"] >= 1
    assert users_after["days"][-1]["registered"] >= 1
    assert sum(users_after["by_status"].values()) == users_after["total"]

    for path in ("/api/v1/admin/stats", "/api/v1/admin/users/stats"):
        assert api.gateway.get(path).status_code == 401
        assert api.gateway.get(path, headers=newcomer.auth).status_code == 403


def test_staff_see_a_customers_wallets_but_cannot_touch_them(
    api: FinCoreClient, user: User
) -> None:
    staff = api.grant_role(api.register_and_login(), "SUPPORT")
    wallet = api.funded_wallet(user, 42_000)
    api.gateway.patch(f"/api/v1/wallets/{wallet}", json={"name": "Salary"}, headers=user.auth)
    url, params = "/api/v1/admin/wallets", {"user_id": user.id}

    seen = api.gateway.get(url, params=params, headers=staff.auth)

    assert seen.status_code == 200
    assert seen.json() == api.gateway.get("/api/v1/wallets", headers=user.auth).json()
    assert [(w["name"], w["balance_minor"]) for w in seen.json()] == [("Salary", 42_000)]
    assert api.gateway.get(url, params=params, headers=user.auth).status_code == 403
    assert api.gateway.get(url, params=params).status_code == 401
    # Staff are not the owner: the customer's own endpoints stay closed to them.
    assert api.gateway.get(f"/api/v1/wallets/{wallet}", headers=staff.auth).status_code == 404
    assert (
        api.gateway.post(f"/api/v1/wallets/{wallet}/block", headers=staff.auth).status_code == 404
    )


def test_the_operations_listing_downloads_as_csv(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    staff = api.grant_role(api.register_and_login(), "SUPPORT")
    source = api.funded_wallet(user, 100_000)
    destination = api.create_wallet(other_user)
    transfer = api.transfer(user, source=source, destination=destination, amount="12.50").json()

    exported = api.gateway.get(
        "/api/v1/admin/transactions/export.csv", params={"user_id": user.id}, headers=staff.auth
    )

    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(exported.content.decode("utf-8-sig"))))
    assert [(row["Reference"], row["Type"], row["Amount"], row["Currency"]) for row in rows] == [
        (transfer["reference"], "TRANSFER", "12.50", "UZS")
    ]
    assert rows[0]["User id"] == user.id
    assert (
        api.gateway.get("/api/v1/admin/transactions/export.csv", headers=user.auth).status_code
        == 403
    )
