import json
from pathlib import Path

from app.main import app

_SERVICE_DIR = Path(__file__).resolve().parents[2]
_CONTRACT = _SERVICE_DIR.parents[1] / "contracts" / "openapi" / f"{_SERVICE_DIR.name}.json"


def test_the_app_matches_its_committed_openapi_contract() -> None:
    """spec Section 26's contract checks: this service's API (public and
    /internal/*) must match contracts/openapi/<service>.json exactly, so
    any change to a route, request or response shape shows up as a
    reviewed contract diff instead of silently breaking a caller.
    """
    committed = json.loads(_CONTRACT.read_text())

    assert app.openapi() == committed, (
        f"{_SERVICE_DIR.name}'s API no longer matches {_CONTRACT.name} — "
        "run scripts/export-openapi.sh and review the contract diff"
    )
