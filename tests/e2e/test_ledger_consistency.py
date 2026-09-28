"""spec Section 23's invariants, checked against the real ledger after
real traffic, by ledger-service's own reconciliation job (spec Section
8.4) rather than re-derived here:

    per posting:  sum(debits) == sum(credits)
    per account:  cached balance == sum of its entries
    per wallet:   available balance never below zero
    per transfer: at most one posting per source_id
"""

from e2e_client import FinCoreClient, User


def test_the_ledger_reconciles_clean_after_a_mixed_workload(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    source = api.funded_wallet(user, 100_000)
    destination = api.create_wallet(other_user)
    merchant_id = api.create_merchant(other_user)

    api.transfer(user, source=source, destination=destination, amount="100.00")
    api.transfer(user, source=source, destination=destination, amount="99999.00")  # fails
    payment = api.pay(user, wallet_id=source, merchant_id=merchant_id, amount="200.00").json()
    api.refund(other_user, payment_id=payment["id"], amount="50.00")
    api.pay(user, wallet_id=source, merchant_id=merchant_id, amount="99999.00")  # fails

    report = api.reconciliation_report()

    assert report["is_clean"], report
    assert report["unbalanced_postings"] == []
    assert report["balance_mismatches"] == []
    assert report["negative_available_wallets"] == []
    assert report["duplicate_source_postings"] == []
    # And the numbers add up from the user's side too.
    assert api.wallet(user, source)["balance_minor"] == 100_000 - 10_000 - 20_000 + 5_000
