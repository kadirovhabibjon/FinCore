"""assistant-service through the gateway. These checks never reach the
Claude API (no key in CI, and no spend locally): what they cover is that
the chat is routed, authenticated and validated like any other API."""

from e2e_client import FinCoreClient, User


def test_the_chat_requires_a_signed_in_customer(api: FinCoreClient) -> None:
    response = api.gateway.post(
        "/api/v1/assistant/chat", json={"messages": [{"role": "user", "content": "hi"}]}
    )
    assert response.status_code == 401


def test_a_malformed_conversation_is_rejected_before_any_model_call(
    api: FinCoreClient, user: User
) -> None:
    response = api.gateway.post(
        "/api/v1/assistant/chat",
        json={"messages": [{"role": "assistant", "content": "I go first"}]},
        headers=user.auth,
    )
    assert response.status_code == 422
    assert response.json()["title"] == "Invalid Conversation"
