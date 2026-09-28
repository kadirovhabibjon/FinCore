"""The asynchronous half of the system: payment-service's transactional
outbox -> Kafka -> consumers (spec Section 14). audit-service is the one
consumer with a read API, so it's where the whole chain is observable
end to end: a committed business change produces exactly one audit row,
some seconds later, with no synchronous call connecting the two.
"""

from typing import Any

from e2e_client import FinCoreClient, User, wait_until


def _single_audit_row(api: FinCoreClient, resource_id: str) -> dict[str, Any] | None:
    rows = api.audit_logs_for(resource_id)
    return rows[0] if rows else None


def test_a_completed_transfer_reaches_the_audit_trail_via_kafka(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    source = api.funded_wallet(user, 10_000)
    destination = api.create_wallet(other_user)
    transfer = api.transfer(user, source=source, destination=destination, amount="12.34").json()

    row = wait_until(lambda: _single_audit_row(api, transfer["id"]), timeout=60)

    assert row["action"] == "TRANSFER_COMPLETED"
    assert row["resource_type"] == "Transfer"
    assert row["actor_id"] == user.id
    assert row["result"] == "COMPLETED"
    assert row["details"]["amount_minor"] == 1_234
    # The correlation id minted at the gateway survived the HTTP hop into
    # payment-service, the outbox row, Kafka, and audit-service's consumer.
    assert row["correlation_id"]


def test_a_failed_transfer_is_audited_too(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    source = api.funded_wallet(user, 100)
    destination = api.create_wallet(other_user)
    transfer = api.transfer(user, source=source, destination=destination, amount="5.00").json()
    assert transfer["status"] == "FAILED"

    row = wait_until(lambda: _single_audit_row(api, transfer["id"]), timeout=60)

    assert row["action"] == "TRANSFER_FAILED"
    assert row["result"] == "FAILED"


def test_payment_and_refund_each_produce_their_own_audit_entry(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    merchant_id = api.create_merchant(other_user)
    wallet = api.funded_wallet(user, 10_000)
    payment = api.pay(user, wallet_id=wallet, merchant_id=merchant_id, amount="40.00").json()
    api.refund(other_user, payment_id=payment["id"], amount="10.00")

    def both_audited() -> list[dict[str, Any]] | None:
        rows = api.audit_logs_for(payment["id"])
        return rows if len(rows) >= 2 else None

    rows = wait_until(both_audited, timeout=60)

    actions = sorted(row["action"] for row in rows)
    assert actions == ["PAYMENT_COMPLETED", "PAYMENT_REFUNDED"]
    # Exactly one row per event — at-least-once delivery never produces a
    # duplicate audit entry (UNIQUE(event_id)).
    assert len({row["event_id"] for row in rows}) == len(rows)
