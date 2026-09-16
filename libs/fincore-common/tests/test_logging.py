import json
import logging

import pytest

from fincore_common.correlation import reset_correlation_id, set_correlation_id
from fincore_common.logging import configure_logging


@pytest.fixture(autouse=True)
def _restore_root_logger():
    original_handlers = logging.getLogger().handlers[:]
    original_level = logging.getLogger().level
    yield
    logging.getLogger().handlers = original_handlers
    logging.getLogger().setLevel(original_level)


def test_configure_logging_emits_json_with_expected_fields(capsys) -> None:
    configure_logging(service_name="identity-service", level="INFO")

    logging.getLogger("test").info("hello world", extra={"user_id": "u-1"})

    line = capsys.readouterr().out.strip()
    payload = json.loads(line)

    assert payload["service"] == "identity-service"
    assert payload["level"] == "INFO"
    assert payload["message"] == "hello world"
    assert payload["logger"] == "test"
    assert payload["user_id"] == "u-1"
    assert "timestamp" in payload


def test_configure_logging_includes_correlation_id_when_set(capsys) -> None:
    configure_logging(service_name="identity-service", level="INFO")
    token = set_correlation_id("corr-abc")
    try:
        logging.getLogger("test").info("inside a request")
    finally:
        reset_correlation_id(token)

    payload = json.loads(capsys.readouterr().out.strip())

    assert payload["correlation_id"] == "corr-abc"


def test_configure_logging_respects_level(capsys) -> None:
    configure_logging(service_name="identity-service", level="WARNING")

    logging.getLogger("test").info("should be filtered out")
    logging.getLogger("test").warning("should appear")

    lines = [line for line in capsys.readouterr().out.strip().splitlines() if line]

    assert len(lines) == 1
    assert json.loads(lines[0])["message"] == "should appear"
