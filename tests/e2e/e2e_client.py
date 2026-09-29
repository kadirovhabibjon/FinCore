"""A thin client over the running stack, used by every e2e test.

Everything a user can do goes through the gateway, exactly as a real
client would. The only calls made directly against a service are the
ones a real client *can't* make — `/internal/*` APIs that are
deliberately not routed through the gateway (spec Section 19): funding a
wallet (there is no public deposit API), reading the audit trail, and
triggering a reconciliation pass. Granting a staff role goes through the
operator CLI inside the identity-service container, for the same reason.
"""

import os
import secrets
import subprocess
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class StackConfig:
    gateway_url: str
    service_urls: dict[str, str]
    ledger_internal_token: str
    audit_internal_token: str


@dataclass(frozen=True)
class User:
    id: str
    email: str
    password: str
    access_token: str
    refresh_token: str

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


def idempotency_key() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid.uuid4())}


def wait_until[T](
    probe: Callable[[], T | None], *, timeout: float = 30.0, interval: float = 0.5
) -> T:
    """Polls `probe` until it returns something other than None — for
    anything that happens asynchronously (outbox relay -> Kafka ->
    consumer), where there's no response to wait on directly.
    """
    deadline = time.monotonic() + timeout
    while True:
        result = probe()
        if result is not None:
            return result
        if time.monotonic() > deadline:
            raise TimeoutError(f"condition not met within {timeout}s")
        time.sleep(interval)


class FinCoreClient:
    def __init__(self, config: StackConfig) -> None:
        self.config = config
        self.gateway = httpx.Client(base_url=config.gateway_url, timeout=15.0)
        self.ledger = httpx.Client(
            base_url=config.service_urls["ledger-service"],
            timeout=15.0,
            headers={"X-Internal-Token": config.ledger_internal_token},
        )
        self.audit = httpx.Client(
            base_url=config.service_urls["audit-service"],
            timeout=15.0,
            headers={"X-Internal-Token": config.audit_internal_token},
        )

    def close(self) -> None:
        self.gateway.close()
        self.ledger.close()
        self.audit.close()

    # --- identity -------------------------------------------------------

    def register_and_login(self) -> User:
        email = f"e2e-{uuid.uuid4().hex[:12]}@example.com"
        password = "E2e-Passw0rd!"
        phone = "+99890" + "".join(secrets.choice("0123456789") for _ in range(7))

        registered = self.gateway.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "phone": phone,
                "password": password,
                "first_name": "E2E",
                "last_name": "User",
            },
        )
        registered.raise_for_status()

        tokens = self.login(email, password)
        return User(
            id=registered.json()["id"],
            email=email,
            password=password,
            access_token=tokens["access_token"],
            refresh_token=tokens["refresh_token"],
        )

    def grant_role(self, user: User, role: str) -> User:
        """No HTTP endpoint grants roles (identity-service's app/cli.py),
        so this runs the operator CLI inside the running container — the
        same thing an operator does — then logs in again, since roles are
        baked into the access token at issue time.
        """
        compose = os.environ.get("E2E_COMPOSE_COMMAND", "docker compose").split()
        subprocess.run(
            [*compose, "exec", "-T", "identity-service", "python", "-m", "app.cli",
             "grant-role", user.email, role],
            check=True,
            capture_output=True,
            cwd=REPO_ROOT,
        )
        tokens = self.login(user.email, user.password)
        return User(
            id=user.id,
            email=user.email,
            password=user.password,
            access_token=tokens["access_token"],
            refresh_token=tokens["refresh_token"],
        )

    def login(self, email: str, password: str) -> dict[str, Any]:
        response = self.gateway.post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        )
        response.raise_for_status()
        return response.json()

    # --- wallets / ledger -----------------------------------------------

    def create_wallet(self, user: User, currency: str = "UZS") -> str:
        response = self.gateway.post(
            "/api/v1/wallets", json={"currency": currency}, headers=user.auth
        )
        response.raise_for_status()
        return str(response.json()["id"])

    def wallet(self, user: User, wallet_id: str) -> dict[str, Any]:
        response = self.gateway.get(f"/api/v1/wallets/{wallet_id}", headers=user.auth)
        response.raise_for_status()
        return response.json()

    def fund_wallet(self, wallet_id: str, amount_minor: int, currency: str = "UZS") -> None:
        """No public deposit API exists (spec Section 20) — money enters
        through ledger-service's internal postings API, debiting the
        EXTERNAL_FUNDING clearing account (ADR-0002).
        """
        funding = self.ledger.get(
            "/internal/v1/accounts/system",
            params={"kind": "EXTERNAL_FUNDING", "currency": currency},
        )
        funding.raise_for_status()
        posted = self.ledger.post(
            "/internal/v1/postings",
            json={
                "source_service": "e2e-tests",
                "source_id": f"fund-{uuid.uuid4()}",
                "type": "DEPOSIT",
                "currency": currency,
                "entries": [
                    {
                        "account_id": funding.json()["id"],
                        "direction": "DEBIT",
                        "amount_minor": amount_minor,
                    },
                    {"account_id": wallet_id, "direction": "CREDIT", "amount_minor": amount_minor},
                ],
            },
        )
        posted.raise_for_status()

    def funded_wallet(self, user: User, amount_minor: int) -> str:
        wallet_id = self.create_wallet(user)
        self.fund_wallet(wallet_id, amount_minor)
        return wallet_id

    def reconciliation_report(self) -> dict[str, Any]:
        response = self.ledger.get("/internal/v1/reconciliation")
        response.raise_for_status()
        return response.json()

    # --- payment-service ------------------------------------------------

    def transfer(
        self,
        user: User,
        *,
        source: str,
        destination: str,
        amount: str,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        return self.gateway.post(
            "/api/v1/transfers",
            json={
                "source_wallet_id": source,
                "destination_wallet_id": destination,
                "amount": amount,
                "currency": "UZS",
            },
            headers={**user.auth, **(headers or idempotency_key())},
        )

    def create_merchant(self, owner: User, name: str = "E2E Shop") -> str:
        response = self.gateway.post("/api/v1/merchants", json={"name": name}, headers=owner.auth)
        response.raise_for_status()
        return str(response.json()["id"])

    def pay(self, payer: User, *, wallet_id: str, merchant_id: str, amount: str) -> httpx.Response:
        return self.gateway.post(
            "/api/v1/payments",
            json={
                "source_wallet_id": wallet_id,
                "merchant_id": merchant_id,
                "amount": amount,
                "currency": "UZS",
            },
            headers={**payer.auth, **idempotency_key()},
        )

    def refund(self, owner: User, *, payment_id: str, amount: str) -> httpx.Response:
        return self.gateway.post(
            f"/api/v1/payments/{payment_id}/refunds",
            json={"amount": amount, "reason": "e2e refund"},
            headers={**owner.auth, **idempotency_key()},
        )

    def get_payment(self, user: User, payment_id: str) -> dict[str, Any]:
        response = self.gateway.get(f"/api/v1/payments/{payment_id}", headers=user.auth)
        response.raise_for_status()
        return response.json()

    # --- audit-service --------------------------------------------------

    def audit_logs_for(self, resource_id: str) -> list[dict[str, Any]]:
        response = self.audit.get("/internal/v1/audit-logs", params={"resource_id": resource_id})
        response.raise_for_status()
        return list(response.json())
