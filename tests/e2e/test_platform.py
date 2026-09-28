"""Cross-cutting behavior that only exists once the whole stack is
assembled: the gateway's routing boundary, correlation ids, and every
service's operational endpoints.
"""

import os

import httpx
import pytest

from e2e_client import FinCoreClient, User, wait_until


def test_the_gateway_answers_its_own_health_check(api: FinCoreClient) -> None:
    response = api.gateway.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize(
    "path",
    [
        "/internal/v1/postings",
        "/internal/v1/reconciliation",
        "/internal/v1/risk-checks",
        "/internal/v1/merchants/00000000-0000-0000-0000-000000000000",
        "/internal/v1/audit-logs",
        "/metrics",
    ],
)
def test_internal_routes_are_not_reachable_through_the_gateway(
    api: FinCoreClient, path: str
) -> None:
    """spec Section 19: /internal/* exists only on the container network,
    never behind the public gateway — the gateway has no route for it at
    all, rather than forwarding and relying on the token check.
    """
    assert api.gateway.get(path).status_code == 404
    assert api.gateway.post(path, json={}).status_code == 404


def test_the_gateway_mints_a_correlation_id_and_echoes_a_supplied_one(
    api: FinCoreClient, user: User
) -> None:
    minted = api.gateway.get("/api/v1/users/me", headers=user.auth)
    supplied = api.gateway.get(
        "/api/v1/users/me", headers={**user.auth, "X-Correlation-ID": "e2e-trace-123"}
    )

    assert minted.headers.get("X-Correlation-ID")
    assert supplied.headers["X-Correlation-ID"] == "e2e-trace-123"


def test_every_service_is_ready_and_exposes_prometheus_metrics(api: FinCoreClient) -> None:
    for service, url in api.config.service_urls.items():
        ready = httpx.get(f"{url}/ready", timeout=5.0)
        metrics = httpx.get(f"{url}/metrics", timeout=5.0)

        assert ready.status_code == 200, service
        assert metrics.status_code == 200, service
        assert f'service="{service}"' in metrics.text, service


def test_prometheus_is_scraping_every_service() -> None:
    prometheus_url = os.environ.get("E2E_PROMETHEUS_URL", "http://localhost:9090")
    try:
        response = httpx.get(f"{prometheus_url}/api/v1/targets", timeout=5.0)
    except httpx.HTTPError:
        pytest.skip("Prometheus not reachable")

    assert response.status_code == 200

    def all_up() -> dict[str, str] | None:
        targets = httpx.get(f"{prometheus_url}/api/v1/targets", timeout=5.0).json()
        health = {t["labels"]["job"]: t["health"] for t in targets["data"]["activeTargets"]}
        # A target stays "unknown" until its first scrape (every 10s).
        return health if set(health.values()) == {"up"} else None

    health = wait_until(all_up, timeout=45, interval=3.0)

    assert len(health) == 7
