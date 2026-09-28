from e2e_client import FinCoreClient, User

# fraud-service's defaults (services/fraud-service/app/core/config.py):
# LARGE_AMOUNT above 500,000.00 UZS adds 30, HIGH_FREQUENCY at 5+ checks
# in the last 60s adds 25. Either alone scores below 40 -> ALLOW; both
# together score 55 -> REVIEW (spec Section 12's 40-69 band).
_LARGE_AMOUNT = "600000.00"
_HIGH_FREQUENCY_THRESHOLD = 5


def test_a_large_transfer_alone_is_still_allowed(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    source = api.funded_wallet(user, 70_000_000)
    destination = api.create_wallet(other_user)

    response = api.transfer(user, source=source, destination=destination, amount=_LARGE_AMOUNT)

    assert response.status_code == 201
    assert response.json()["fraud_decision"] == "ALLOW"
    assert response.json()["status"] == "COMPLETED"


def test_a_large_transfer_after_a_burst_goes_to_review_and_moves_no_money(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    """Two independent rules firing together — a real risk decision made
    by the real fraud-service, reached through the gateway and the
    transfer saga, not a stubbed client.
    """
    source = api.funded_wallet(user, 70_000_000)
    destination = api.create_wallet(other_user)
    for _ in range(_HIGH_FREQUENCY_THRESHOLD):
        burst = api.transfer(user, source=source, destination=destination, amount="1.00")
        assert burst.json()["status"] == "COMPLETED"
    balance_before = api.wallet(user, source)["balance_minor"]

    response = api.transfer(user, source=source, destination=destination, amount=_LARGE_AMOUNT)

    assert response.status_code == 201
    transfer = response.json()
    assert transfer["fraud_decision"] == "REVIEW"
    # spec Section 10.1: REVIEW stops the saga before the ledger is
    # ever called — the transfer waits, and no money moves.
    assert transfer["status"] == "PENDING"
    assert api.wallet(user, source)["balance_minor"] == balance_before
