"""Consumer side of contracts/openapi: payment-service's real transfer,
payment, refund and recovery code paths, run against ledger-service and
fraud-service fakes that enforce those services' committed OpenAPI
contracts (tests/contracts.py's ContractFake). Unlike the hand-written
fakes elsewhere in this suite — which exercise saga *behavior* — these
prove every request payment-service actually builds is one the real
providers would accept, and that it correctly reads responses shaped
exactly as those providers promise.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app
from app.services import fraud, ledger
from tests.contracts import ContractFake

pytestmark = pytest.mark.usefixtures("migrated_database")

_NOW = datetime.now(UTC)
_SETTLEMENT_ACCOUNT = str(uuid.uuid4())
_HOLD_ID = str(uuid.uuid4())


def _wallet(wallet_id: str) -> dict:
    return {
        "id": wallet_id,
        "currency": "UZS",
        "status": "ACTIVE",
        "created_at": _NOW.isoformat(),
        "balance_minor": 1_000_000,
        "held_minor": 0,
    }


def _posting(source_id: str = "src", type_: str = "TRANSFER") -> dict:
    return {
        "id": str(uuid.uuid4()),
        "source_service": "payment-service",
        "source_id": source_id,
        "type": type_,
        "currency": "UZS",
        "created_at": _NOW.isoformat(),
    }


def _hold(status: str = "ACTIVE") -> dict:
    return {
        "id": _HOLD_ID,
        "account_id": str(uuid.uuid4()),
        "amount_minor": 10_000,
        "currency": "UZS",
        "status": status,
        "created_at": _NOW.isoformat(),
        "expires_at": (_NOW + timedelta(minutes=15)).isoformat(),
        "resolved_at": None if status == "ACTIVE" else _NOW.isoformat(),
    }


def _ledger_fake(source_wallet: str) -> ContractFake:
    return ContractFake(
        provider="ledger-service",
        responses={
            ("GET", "/api/v1/wallets/{wallet_id}"): (200, _wallet(source_wallet)),
            ("POST", "/internal/v1/postings"): (201, _posting()),
            ("GET", "/internal/v1/postings/{source_id}"): (200, _posting()),
            ("POST", "/internal/v1/holds"): (201, _hold()),
            ("POST", "/internal/v1/holds/{hold_id}/capture"): (200, _posting(type_="PAYMENT")),
            ("POST", "/internal/v1/holds/{hold_id}/release"): (200, _hold("RELEASED")),
            ("GET", "/internal/v1/accounts/system"): (
                200,
                {"id": _SETTLEMENT_ACCOUNT, "kind": "MERCHANT_SETTLEMENT", "currency": "UZS"},
            ),
        },
    )


def _fraud_fake() -> ContractFake:
    return ContractFake(
        provider="fraud-service",
        responses={
            ("POST", "/internal/v1/risk-checks"): (
                201,
                {
                    "id": str(uuid.uuid4()),
                    "decision": "ALLOW",
                    "score": 0,
                    "rules_triggered": [],
                    "created_at": _NOW.isoformat(),
                },
            )
        },
    )


def _wire(
    monkeypatch: pytest.MonkeyPatch, ledger_fake: ContractFake, fraud_fake: ContractFake
) -> None:
    monkeypatch.setattr(
        ledger,
        "ledger_client",
        ledger.LedgerClient(
            base_url="http://ledger",
            internal_token=settings.internal_service_token,
            timeout_seconds=2.0,
            transport=ledger_fake.transport(),
        ),
    )
    monkeypatch.setattr(
        fraud,
        "fraud_client",
        fraud.FraudClient(
            base_url="http://fraud",
            internal_token=settings.internal_service_token,
            timeout_seconds=2.0,
            fail_open_limit_minor=settings.fraud_fail_open_limit_minor,
            transport=fraud_fake.transport(),
        ),
    )


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid.uuid4())}


async def test_the_transfer_saga_speaks_ledger_and_fraud_contracts(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    source = str(uuid.uuid4())
    ledger_fake, fraud_fake = _ledger_fake(source), _fraud_fake()
    _wire(monkeypatch, ledger_fake, fraud_fake)
    token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        response = await client.post(
            "/api/v1/transfers",
            json={
                "source_wallet_id": source,
                "destination_wallet_id": str(uuid.uuid4()),
                "amount": "100.00",
                "currency": "UZS",
            },
            headers=_headers(token),
        )

    assert response.status_code == 201, response.text
    assert response.json()["status"] == "COMPLETED"
    assert ledger_fake.calls == [
        ("GET", "/api/v1/wallets/{wallet_id}"),
        ("POST", "/internal/v1/postings"),
    ]
    assert fraud_fake.calls == [("POST", "/internal/v1/risk-checks")]


async def test_the_payment_and_refund_sagas_speak_the_ledger_contract(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    source = str(uuid.uuid4())
    ledger_fake, fraud_fake = _ledger_fake(source), _fraud_fake()
    _wire(monkeypatch, ledger_fake, fraud_fake)
    payer_token = issue_access_token(uuid.uuid4())
    owner_token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        merchant = await client.post(
            "/api/v1/merchants",
            json={"name": "Contract Shop"},
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        payment = await client.post(
            "/api/v1/payments",
            json={
                "source_wallet_id": source,
                "merchant_id": merchant.json()["id"],
                "amount": "100.00",
                "currency": "UZS",
            },
            headers=_headers(payer_token),
        )
        assert payment.status_code == 201, payment.text
        assert payment.json()["status"] == "SUCCESS"

        refund = await client.post(
            f"/api/v1/payments/{payment.json()['id']}/refunds",
            json={"amount": "40.00"},
            headers=_headers(owner_token),
        )

    assert refund.status_code == 201, refund.text
    assert refund.json()["status"] == "COMPLETED"
    assert ledger_fake.calls == [
        ("GET", "/api/v1/wallets/{wallet_id}"),
        ("POST", "/internal/v1/holds"),
        ("POST", "/internal/v1/holds/{hold_id}/capture"),
        ("GET", "/internal/v1/accounts/system"),
        ("POST", "/internal/v1/postings"),
    ]


async def test_recovery_and_cleanup_calls_speak_the_ledger_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The two calls no happy-path saga makes: the recovery worker's
    posting lookup (spec Section 10.1) and the best-effort hold release
    after a failed capture.
    """
    ledger_fake = _ledger_fake(str(uuid.uuid4()))
    _wire(monkeypatch, ledger_fake, _fraud_fake())

    found = await ledger.ledger_client.get_posting(
        source_service="payment-service", source_id=str(uuid.uuid4()), type="TRANSFER"
    )
    await ledger.ledger_client.release_hold(uuid.UUID(_HOLD_ID))

    assert found.posting_id is not None
    assert ledger_fake.calls == [
        ("GET", "/internal/v1/postings/{source_id}"),
        ("POST", "/internal/v1/holds/{hold_id}/release"),
    ]
