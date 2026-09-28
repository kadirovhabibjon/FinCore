"""FinCore load test (spec Section 27, Phase 6: "Load testing").

Every simulated user registers, gets a funded wallet and its own
merchant, then runs a mixed workload through the gateway:

    transfers to other users' wallets     (the core money movement)
    payments to other users' merchants    (hold -> capture)
    refunds of payments to their merchant (merchant-side)
    idempotent replays of a transfer      (same key sent twice)
    wallet / transaction-history reads

Transfers go between random pairs of users, so concurrent transfers in
*opposite directions* between the same two wallets happen naturally —
exactly the case ledger-service's ascending-account-id lock ordering
exists for (a deadlock there would surface here as errors or timeouts).

The run fails (non-zero exit code) if the failure ratio or p95 latency
exceeds its threshold, or — the check that actually matters for a
ledger — if ledger-service's reconciliation job finds any violated
invariant once the load stops.

    locust -f locustfile.py --host http://localhost:8180 \
        --headless -u 50 -r 5 -t 2m

Thresholds and URLs come from the environment; see README ("Load testing").
"""

import logging
import os
import random
import secrets
import threading
import uuid
from pathlib import Path
from typing import Any

import httpx
from locust import HttpUser, between, events, task
from locust.env import Environment

REPO_ROOT = Path(__file__).resolve().parents[2]
LEDGER_URL = os.environ.get("LOAD_LEDGER_URL", "http://localhost:8092")
MAX_FAILURE_RATIO = float(os.environ.get("LOAD_MAX_FAILURE_RATIO", "0.01"))
MAX_P95_MS = float(os.environ.get("LOAD_MAX_P95_MS", "1000"))
STARTING_BALANCE_MINOR = 1_000_000  # 10,000.00 UZS — far more than a run spends
AUTH_RETRIES = 10

# httpx logs every setup call (funding, reconciliation) at INFO.
logging.getLogger("httpx").setLevel(logging.WARNING)


def _ledger_token() -> str:
    if token := os.environ.get("LOAD_LEDGER_INTERNAL_TOKEN"):
        return token
    for line in (REPO_ROOT / "services" / "ledger-service" / ".env").read_text().splitlines():
        if line.startswith("INTERNAL_SERVICE_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("no ledger INTERNAL_SERVICE_TOKEN — set LOAD_LEDGER_INTERNAL_TOKEN")


_ledger = httpx.Client(
    base_url=LEDGER_URL, timeout=15.0, headers={"X-Internal-Token": _ledger_token()}
)

# Shared across all simulated users (gevent greenlets in one process).
_lock = threading.Lock()
_wallets: list[str] = []
_merchants: list[str] = []
_payments_by_merchant: dict[str, list[str]] = {}


def _fund(wallet_id: str) -> None:
    """No public deposit API exists (spec Section 20) — setup money enters
    through ledger-service's internal API, outside the measured workload.
    """
    funding = _ledger.get(
        "/internal/v1/accounts/system", params={"kind": "EXTERNAL_FUNDING", "currency": "UZS"}
    )
    funding.raise_for_status()
    _ledger.post(
        "/internal/v1/postings",
        json={
            "source_service": "load-test",
            "source_id": f"fund-{uuid.uuid4()}",
            "type": "DEPOSIT",
            "currency": "UZS",
            "entries": [
                {
                    "account_id": funding.json()["id"],
                    "direction": "DEBIT",
                    "amount_minor": STARTING_BALANCE_MINOR,
                },
                {
                    "account_id": wallet_id,
                    "direction": "CREDIT",
                    "amount_minor": STARTING_BALANCE_MINOR,
                },
            ],
        },
    ).raise_for_status()


class FinCoreCustomer(HttpUser):
    wait_time = between(0.5, 2.0)

    def on_start(self) -> None:
        email = f"load-{uuid.uuid4().hex[:12]}@example.com"
        password = "Load-Passw0rd!"
        phone = "+99891" + "".join(secrets.choice("0123456789") for _ in range(7))
        self._auth_call(
            "/api/v1/auth/register",
            {
                "email": email,
                "phone": phone,
                "password": password,
                "first_name": "Load",
                "last_name": "User",
            },
        )
        tokens = self._auth_call("/api/v1/auth/login", {"email": email, "password": password})
        self.auth = {"Authorization": f"Bearer {tokens['access_token']}"}

        wallet = self.client.post(
            "/api/v1/wallets", json={"currency": "UZS"}, headers=self.auth, name="POST /wallets"
        )
        wallet.raise_for_status()
        self.wallet_id: str = wallet.json()["id"]
        _fund(self.wallet_id)

        merchant = self.client.post(
            "/api/v1/merchants", json={"name": "Load Shop"}, headers=self.auth,
            name="POST /merchants",
        )
        merchant.raise_for_status()
        self.merchant_id: str = merchant.json()["id"]

        with _lock:
            _wallets.append(self.wallet_id)
            _merchants.append(self.merchant_id)
            _payments_by_merchant[self.merchant_id] = []

    def _auth_call(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        """The gateway rate-limits /auth/* per client IP (10r/s, burst 20)
        — every simulated user shares this machine's IP, so a fast spawn
        rate trips it by design. A limited attempt is retried and
        recorded under its own name, so the report shows how often the
        limiter engaged without counting a working protection as an
        error.
        """
        for _ in range(AUTH_RETRIES):
            with self.client.post(path, json=body, catch_response=True, name=f"POST {path}") as r:
                if r.status_code in (429, 503):
                    r.success()
                    r.request_meta["name"] = f"POST {path} [rate-limited, retried]"
                    self.wait()
                    continue
                if r.status_code >= 400:
                    r.failure(f"{r.status_code}: {r.text[:200]}")
                    r.raise_for_status()
                return dict(r.json())
        raise RuntimeError(f"{path} still rate-limited after {AUTH_RETRIES} attempts")

    def _other(self, pool: list[str], mine: str) -> str | None:
        with _lock:
            candidates = [item for item in pool if item != mine]
        return random.choice(candidates) if candidates else None

    def _transfer_body(self, destination: str) -> dict[str, str]:
        return {
            "source_wallet_id": self.wallet_id,
            "destination_wallet_id": destination,
            "amount": f"{random.randint(1, 20)}.{random.randint(0, 99):02d}",
            "currency": "UZS",
        }

    @task(6)
    def transfer(self) -> None:
        destination = self._other(_wallets, self.wallet_id)
        if destination is None:
            return
        with self.client.post(
            "/api/v1/transfers",
            json=self._transfer_body(destination),
            headers={**self.auth, "Idempotency-Key": str(uuid.uuid4())},
            catch_response=True,
            name="POST /transfers",
        ) as r:
            if r.status_code != 201 or r.json()["status"] != "COMPLETED":
                r.failure(f"{r.status_code}: {r.text[:200]}")

    @task(1)
    def replayed_transfer(self) -> None:
        """spec Section 9.1 under load: the same Idempotency-Key twice must
        return the same transfer and move money once.
        """
        destination = self._other(_wallets, self.wallet_id)
        if destination is None:
            return
        body = self._transfer_body(destination)
        headers = {**self.auth, "Idempotency-Key": str(uuid.uuid4())}
        first = self.client.post(
            "/api/v1/transfers", json=body, headers=headers, name="POST /transfers [replay 1]"
        )
        with self.client.post(
            "/api/v1/transfers", json=body, headers=headers, catch_response=True,
            name="POST /transfers [replay 2]",
        ) as second:
            if first.status_code != 201 or second.status_code != 201:
                second.failure(f"{first.status_code}/{second.status_code}")
            elif first.json()["id"] != second.json()["id"]:
                second.failure("replay created a second transfer")

    @task(3)
    def pay(self) -> None:
        merchant_id = self._other(_merchants, self.merchant_id)
        if merchant_id is None:
            return
        with self.client.post(
            "/api/v1/payments",
            json={
                "source_wallet_id": self.wallet_id,
                "merchant_id": merchant_id,
                "amount": "5.00",
                "currency": "UZS",
            },
            headers={**self.auth, "Idempotency-Key": str(uuid.uuid4())},
            catch_response=True,
            name="POST /payments",
        ) as r:
            if r.status_code != 201 or r.json()["status"] != "SUCCESS":
                r.failure(f"{r.status_code}: {r.text[:200]}")
                return
        with _lock:
            _payments_by_merchant[merchant_id].append(r.json()["id"])

    @task(1)
    def refund(self) -> None:
        with _lock:
            received = _payments_by_merchant.get(self.merchant_id, [])
            payment_id = received.pop() if received else None
        if payment_id is None:
            return
        with self.client.post(
            f"/api/v1/payments/{payment_id}/refunds",
            json={"amount": "1.00", "reason": "load test"},
            headers={**self.auth, "Idempotency-Key": str(uuid.uuid4())},
            catch_response=True,
            name="POST /payments/{id}/refunds",
        ) as r:
            if r.status_code != 201 or r.json()["status"] != "COMPLETED":
                r.failure(f"{r.status_code}: {r.text[:200]}")

    @task(3)
    def read_wallet(self) -> None:
        self.client.get(
            f"/api/v1/wallets/{self.wallet_id}", headers=self.auth, name="GET /wallets/{id}"
        )

    @task(2)
    def read_history(self) -> None:
        self.client.get("/api/v1/transactions", headers=self.auth, name="GET /transactions")


@events.quitting.add_listener
def _verify(environment: Environment, **_: Any) -> None:
    """Pass/fail for the whole run. Latency and error thresholds are the
    usual load-test gates; the reconciliation check is the one specific
    to a ledger — money must still add up after everything ran
    concurrently.
    """
    stats = environment.stats.total
    problems = []
    if stats.fail_ratio > MAX_FAILURE_RATIO:
        problems.append(f"failure ratio {stats.fail_ratio:.2%} > {MAX_FAILURE_RATIO:.2%}")
    p95 = stats.get_response_time_percentile(0.95) or 0.0
    if p95 > MAX_P95_MS:
        problems.append(f"p95 {p95:.0f}ms > {MAX_P95_MS:.0f}ms")

    report = _ledger.get("/internal/v1/reconciliation")
    report.raise_for_status()
    reconciliation = report.json()
    if not reconciliation["is_clean"]:
        problems.append(f"ledger reconciliation found violations: {reconciliation}")

    print("\n=== FinCore load test verdict ===")
    print(f"requests: {stats.num_requests}, failures: {stats.num_failures} "
          f"({stats.fail_ratio:.2%}), p50: {stats.median_response_time:.0f}ms, "
          f"p95: {p95:.0f}ms, rps: {stats.total_rps:.1f}")
    print(f"ledger reconciliation: {'clean' if reconciliation['is_clean'] else 'VIOLATIONS'}")
    for problem in problems:
        print(f"FAIL: {problem}")
    if problems:
        environment.process_exit_code = 1
    else:
        print("PASS")
