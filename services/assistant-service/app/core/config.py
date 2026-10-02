from fincore_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "assistant-service"

    # Claude API. Empty means "not configured": the service still starts and
    # reports healthy, and the chat endpoint answers 503 until a key is set.
    anthropic_api_key: str = ""
    assistant_model: str = "claude-opus-5-5"
    # Thinking is always on for this model; effort is the depth control
    # (its default is "medium" - set explicitly so a model change can't
    # silently move it).
    assistant_effort: str = "medium"
    assistant_max_tokens: int = 16000
    # Upper bound on Claude <-> tool round trips in one reply.
    assistant_max_tool_rounds: int = 8

    # What one chat request may carry.
    max_history_messages: int = 20
    max_message_chars: int = 2000

    # Per-customer cap on chat requests (each one costs real API spend).
    rate_limit_requests: int = 30
    rate_limit_window_seconds: int = 3600

    # The public APIs the tools read, called with the customer's own bearer
    # token: each service authorizes the request exactly as it would for
    # the web app, so the assistant can never see more than the customer.
    identity_service_base_url: str = "http://localhost:8091"
    ledger_service_base_url: str = "http://localhost:8092"
    payment_service_base_url: str = "http://localhost:8093"
    upstream_timeout_seconds: float = 5.0

    identity_service_jwks_url: str
    jwt_issuer: str = "fincore-identity-service"


settings = Settings()  # type: ignore[call-arg]
