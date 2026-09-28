"""Contract-test helpers (spec Sections 23 and 26: "contract tests — API
and event schemas between services"). Validates payloads against the
repo's committed contracts:

- contracts/events/*.json   — JSON Schemas for every Kafka event
- contracts/openapi/*.json  — every service's own API, exported from its
                              app and kept honest by that service's
                              tests/unit/test_openapi_contract.py

The same module is copied into each service that produces or consumes a
contract (services never import each other's code).
"""

import copy
import json
import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

import httpx
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

CONTRACTS_DIR = Path(__file__).resolve().parents[3] / "contracts"


def _assert_valid(schema: dict[str, Any], instance: Any, registry: Registry, what: str) -> None:
    validator = Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.path))
    assert not errors, f"{what} violates its contract:\n" + "\n".join(
        f"  at {'/'.join(map(str, error.path)) or '<root>'}: {error.message}" for error in errors
    )


# --- events ------------------------------------------------------------


@cache
def event_schema(name: str, version: int = 1) -> dict[str, Any]:
    return json.loads((CONTRACTS_DIR / "events" / f"{name}.v{version}.json").read_text())


def event_example(event_type: str) -> dict[str, Any]:
    """The contract's own canonical payload — what a consumer test feeds
    its handler, so a consumer is tested against what the contract
    promises rather than against a fixture it wrote itself.
    """
    return copy.deepcopy(event_schema(event_type)["examples"][0])


def assert_valid_event(envelope: dict[str, Any]) -> None:
    """`envelope` as it goes on the wire (EventEnvelope.model_dump(mode="json"))."""
    _assert_valid(event_schema("envelope"), envelope, Registry(), "event envelope")
    _assert_valid(
        event_schema(envelope["event_type"], envelope["event_version"]),
        envelope["data"],
        Registry(),
        f"{envelope['event_type']} payload",
    )


# --- HTTP APIs ---------------------------------------------------------


@cache
def _openapi(provider: str) -> tuple[dict[str, Any], Registry]:
    document = json.loads((CONTRACTS_DIR / "openapi" / f"{provider}.json").read_text())
    resource = Resource.from_contents(document, default_specification=DRAFT202012)
    return document, Registry().with_resource(f"urn:openapi:{provider}", resource)


def _pointer(*parts: str) -> str:
    return "/".join(part.replace("~", "~0").replace("/", "~1") for part in parts)


def _match_operation(document: dict[str, Any], method: str, path: str) -> tuple[str, dict]:
    for template, operations in document["paths"].items():
        pattern = "^" + re.sub(r"\{[^/]+\}", "[^/]+", template) + "$"
        if re.match(pattern, path) and method.lower() in operations:
            return template, operations[method.lower()]
    raise AssertionError(f"{method} {path} is not an operation in the provider's contract")


@dataclass
class ContractFake:
    """An httpx transport standing in for `provider`, which fails the test
    the moment a request doesn't match the provider's committed OpenAPI
    contract — unknown route, missing required query parameter, or a
    body the provider would reject — and which only hands back canned
    responses that themselves satisfy the provider's documented response
    schema. A consumer that passes against this is compatible with what
    the provider actually promises, not with a hand-written fake that
    could have drifted from it.

    `responses` maps (METHOD, path template) -> (status, body).
    """

    provider: str
    responses: dict[tuple[str, str], tuple[int, Any]]
    calls: list[tuple[str, str]] = field(default_factory=list)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        document, registry = _openapi(self.provider)
        template, operation = _match_operation(document, request.method, request.url.path)
        method = request.method.lower()
        base = f"urn:openapi:{self.provider}#/" + _pointer("paths", template, method)

        for parameter in operation.get("parameters", []):
            if not parameter.get("required"):
                continue
            if parameter["in"] == "query":
                assert parameter["name"] in request.url.params, (
                    f"{request.method} {template}: missing required query "
                    f"parameter {parameter['name']!r}"
                )
            elif parameter["in"] == "header":
                assert parameter["name"] in request.headers, (
                    f"{request.method} {template}: missing required header "
                    f"{parameter['name']!r}"
                )

        if "requestBody" in operation:
            body = json.loads(request.content) if request.content else None
            body_schema = _pointer("requestBody", "content", "application/json", "schema")
            _assert_valid(
                {"$ref": f"{base}/{body_schema}"},
                body,
                registry,
                f"request to {request.method} {template}",
            )

        assert (request.method, template) in self.responses, (
            f"test made an unexpected call: {request.method} {template}"
        )
        status, response_body = self.responses[(request.method, template)]
        documented = operation["responses"].get(str(status), {}).get("content", {})
        assert "application/json" in documented, (
            f"{request.method} {template}: {status} is not a documented response"
        )
        response_schema = _pointer(
            "responses", str(status), "content", "application/json", "schema"
        )
        _assert_valid(
            {"$ref": f"{base}/{response_schema}"},
            response_body,
            registry,
            f"canned {status} response for {request.method} {template}",
        )

        self.calls.append((request.method, template))
        return httpx.Response(status, json=response_body)
