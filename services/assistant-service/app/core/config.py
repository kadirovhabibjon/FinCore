from typing import Literal

from fincore_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "assistant-service"

    # Which model API answers the chat:
    #   "anthropic"          - Claude (the settings just below);
    #   "openai_compatible"  - any Chat Completions API with tool calling,
    #                          such as Google Gemini's or Groq's, both of
    #                          which have a free tier (the LLM_* settings).
    assistant_provider: Literal["anthropic", "openai_compatible"] = "anthropic"

    # OpenAI-compatible provider. Like the Claude key, an empty key means
    # "not configured": the chat answers 503 until one is set.
    llm_api_key: str = ""
    llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    llm_model: str = "gemini-flash-latest"
    # Tried in order when the model above is overloaded, over its quota or
    # retired (free tiers do all three), comma-separated.
    llm_fallback_models: str = "gemini-flash-lite-latest"
    llm_max_tokens: int = 4096
    llm_timeout_seconds: float = 60.0

    # Claude API. Empty means "not configured": the service still starts and
    # reports healthy, and the chat endpoint answers 503 until a key is set.
    anthropic_api_key: str = ""
    # Needed only for a key that isn't scoped to a workspace (a user key,
    # "sk-ant-usr-..."): the API then requires the workspace to bill and
    # rate-limit against on every request. Console → Settings → Workspaces.
    anthropic_workspace_id: str = ""
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

    @property
    def assistant_configured(self) -> bool:
        """Whether the selected provider has a key to answer with."""
        if self.assistant_provider == "openai_compatible":
            return bool(self.llm_api_key)
        return bool(self.anthropic_api_key)


settings = Settings()  # type: ignore[call-arg]
