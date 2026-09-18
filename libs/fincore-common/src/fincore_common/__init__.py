from .auth import (
    InvalidInternalTokenError,
    InvalidTokenError,
    JWTVerifier,
    require_internal_token,
)
from .config import BaseServiceSettings
from .correlation import (
    HEADER_NAME,
    CorrelationIdMiddleware,
    get_correlation_id,
    new_correlation_id,
    reset_correlation_id,
    set_correlation_id,
)
from .errors import DomainError, ProblemDetail, register_error_handlers
from .events import EventEnvelope, EventType
from .logging import JSONFormatter, configure_logging

# .kafka (EventProducer, EventConsumer) is deliberately not imported
# here: it needs aiokafka, an optional extra (`fincore-common[kafka]`)
# that not every service installs (identity-service and ledger-service
# don't produce or consume events yet). A service that does needs it
# imports `from fincore_common.kafka import ...` directly.
from .money import (
    SUPPORTED_CURRENCIES,
    InvalidAmountError,
    UnsupportedCurrencyError,
    decimal_to_minor,
    minor_to_decimal,
    minor_unit_exponent,
    parse_decimal_string,
)
from .tracing import configure_tracing

__all__ = [
    "InvalidInternalTokenError",
    "InvalidTokenError",
    "JWTVerifier",
    "require_internal_token",
    "BaseServiceSettings",
    "HEADER_NAME",
    "CorrelationIdMiddleware",
    "get_correlation_id",
    "new_correlation_id",
    "reset_correlation_id",
    "set_correlation_id",
    "DomainError",
    "ProblemDetail",
    "register_error_handlers",
    "EventEnvelope",
    "EventType",
    "JSONFormatter",
    "configure_logging",
    "SUPPORTED_CURRENCIES",
    "InvalidAmountError",
    "UnsupportedCurrencyError",
    "decimal_to_minor",
    "minor_to_decimal",
    "minor_unit_exponent",
    "parse_decimal_string",
    "configure_tracing",
]
