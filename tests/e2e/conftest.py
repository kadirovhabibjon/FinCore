"""E2E fixtures. These tests never start the stack themselves — they run
against whatever `docker compose up -d --build` already brought up, the
same way a real client would, and fail fast with a clear message if it
isn't there.

Every URL and token can be overridden by environment variable; the
defaults match docker-compose.yml's host ports and read each internal
token straight out of the service's own `.env` (the same file
docker-compose itself hands that service), so a local run needs no
extra configuration.
"""

import os
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from e2e_client import FinCoreClient, StackConfig, User

REPO_ROOT = Path(__file__).resolve().parents[2]

_SERVICE_PORTS = {
    "identity-service": 8091,
    "ledger-service": 8092,
    "payment-service": 8093,
    "notification-service": 8094,
    "fraud-service": 8095,
    "webhook-service": 8097,
    "audit-service": 8098,
    "assistant-service": 8099,
}


def _env_file_value(service: str, key: str) -> str:
    env_file = REPO_ROOT / "services" / service / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError(
        f"{key} not found in {env_file} — run scripts/generate-dev-env.sh, "
        f"or set it via the environment"
    )


def _config() -> StackConfig:
    host = os.environ.get("E2E_HOST", "localhost")
    return StackConfig(
        gateway_url=os.environ.get("E2E_GATEWAY_URL", f"http://{host}:8180"),
        service_urls={
            name: os.environ.get(
                f"E2E_{name.upper().replace('-', '_')}_URL", f"http://{host}:{port}"
            )
            for name, port in _SERVICE_PORTS.items()
        },
        ledger_internal_token=os.environ.get("E2E_LEDGER_INTERNAL_TOKEN")
        or _env_file_value("ledger-service", "INTERNAL_SERVICE_TOKEN"),
        audit_internal_token=os.environ.get("E2E_AUDIT_INTERNAL_TOKEN")
        or _env_file_value("audit-service", "INTERNAL_SERVICE_TOKEN"),
    )


def _wait_for_stack(config: StackConfig, timeout: float) -> None:
    """Every service's /ready (DB + Kafka, spec Section 24), plus the
    gateway's own /health — not just "the containers are running",
    since a container can be up long before it can serve traffic.
    """
    targets = [f"{config.gateway_url}/health"] + [
        f"{url}/ready" for url in config.service_urls.values()
    ]
    deadline = time.monotonic() + timeout
    pending = list(targets)
    while pending:
        still_pending = []
        for url in pending:
            try:
                if httpx.get(url, timeout=3.0).status_code != 200:
                    still_pending.append(url)
            except httpx.HTTPError:
                still_pending.append(url)
        pending = still_pending
        if pending and time.monotonic() > deadline:
            pytest.exit(
                "FinCore stack not ready after "
                f"{timeout:.0f}s — is it running? (`docker compose up -d --build`)\n"
                "Still not ready: " + ", ".join(pending),
                returncode=1,
            )
        if pending:
            time.sleep(2.0)


@pytest.fixture(scope="session")
def stack_config() -> StackConfig:
    config = _config()
    _wait_for_stack(config, timeout=float(os.environ.get("E2E_READY_TIMEOUT", "180")))
    return config


@pytest.fixture(scope="session")
def api(stack_config: StackConfig) -> Iterator[FinCoreClient]:
    client = FinCoreClient(stack_config)
    yield client
    client.close()


@pytest.fixture
def user(api: FinCoreClient) -> User:
    return api.register_and_login()


@pytest.fixture
def other_user(api: FinCoreClient) -> User:
    return api.register_and_login()
