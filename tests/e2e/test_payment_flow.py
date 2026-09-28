from e2e_client import FinCoreClient, User


def test_a_payment_captures_funds_from_the_payers_wallet(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    merchant_id = api.create_merchant(other_user)
    wallet = api.funded_wallet(user, 50_000)

    response = api.pay(user, wallet_id=wallet, merchant_id=merchant_id, amount="120.00")

    assert response.status_code == 201
    payment = response.json()
    assert payment["status"] == "SUCCESS"
    wallet_after = api.wallet(user, wallet)
    assert wallet_after["balance_minor"] == 38_000
    # Hold reserved then captured (spec Section 11) — nothing left held.
    assert wallet_after["held_minor"] == 0


def test_partial_then_full_refund_returns_money_to_the_payer(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    merchant_id = api.create_merchant(other_user)
    wallet = api.funded_wallet(user, 10_000)
    payment = api.pay(user, wallet_id=wallet, merchant_id=merchant_id, amount="80.00").json()

    partial = api.refund(other_user, payment_id=payment["id"], amount="30.00")
    assert partial.status_code == 201
    assert partial.json()["status"] == "COMPLETED"
    assert api.get_payment(user, payment["id"])["status"] == "PARTIALLY_REFUNDED"
    assert api.wallet(user, wallet)["balance_minor"] == 5_000

    rest = api.refund(other_user, payment_id=payment["id"], amount="50.00")
    assert rest.status_code == 201
    assert api.get_payment(user, payment["id"])["status"] == "REFUNDED"
    assert api.wallet(user, wallet)["balance_minor"] == 10_000


def test_refunding_more_than_was_captured_is_rejected(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    merchant_id = api.create_merchant(other_user)
    wallet = api.funded_wallet(user, 10_000)
    payment = api.pay(user, wallet_id=wallet, merchant_id=merchant_id, amount="20.00").json()

    response = api.refund(other_user, payment_id=payment["id"], amount="20.01")

    assert response.status_code == 422
    assert api.get_payment(user, payment["id"])["status"] == "SUCCESS"


def test_only_the_merchant_owner_can_refund(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    merchant_id = api.create_merchant(other_user)
    wallet = api.funded_wallet(user, 10_000)
    payment = api.pay(user, wallet_id=wallet, merchant_id=merchant_id, amount="20.00").json()

    # The payer is not the merchant — same anti-enumeration 404 as every
    # other ownership check in the system.
    response = api.refund(user, payment_id=payment["id"], amount="5.00")

    assert response.status_code == 404
    assert api.wallet(user, wallet)["balance_minor"] == 8_000


def test_a_payment_without_enough_funds_fails_and_holds_nothing(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    merchant_id = api.create_merchant(other_user)
    wallet = api.funded_wallet(user, 1_000)

    response = api.pay(user, wallet_id=wallet, merchant_id=merchant_id, amount="99.00")

    assert response.status_code == 201
    assert response.json()["status"] == "FAILED"
    wallet_after = api.wallet(user, wallet)
    assert wallet_after["balance_minor"] == 1_000
    assert wallet_after["held_minor"] == 0
