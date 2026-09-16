from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from .correlation import get_correlation_id

# Attributes every stdlib LogRecord carries. Anything else on the record
# came from `logger.info(msg, extra={...})` and should be included verbatim.
_STANDARD_RECORD_KEYS = frozenset(logging.makeLogRecord({}).__dict__.keys()) | {
    "message"
}


class JSONFormatter(logging.Formatter):
    def __init__(self, service_name: str) -> None:
        super().__init__()
        self._service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "service": self._service_name,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": get_correlation_id(),
        }

        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_RECORD_KEYS
        }
        payload.update(extras)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(service_name: str, level: str = "INFO") -> None:
    """Replace the root logger's handlers with a single JSON stdout handler.

    Called once at service startup. Every `logging.getLogger(...)` call
    anywhere in the service (and in fincore-common itself) then produces
    structured JSON lines carrying the current request's correlation ID.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter(service_name))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
