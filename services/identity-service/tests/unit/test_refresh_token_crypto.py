from app.core.security import generate_refresh_token, hash_refresh_token


def test_generate_refresh_token_is_long_and_random() -> None:
    first = generate_refresh_token()
    second = generate_refresh_token()

    assert first != second
    assert len(first) >= 32  # base64url of 32 bytes is well over 32 chars


def test_hash_refresh_token_is_deterministic() -> None:
    token = generate_refresh_token()

    assert hash_refresh_token(token) == hash_refresh_token(token)


def test_hash_refresh_token_differs_for_different_tokens() -> None:
    first = generate_refresh_token()
    second = generate_refresh_token()

    assert hash_refresh_token(first) != hash_refresh_token(second)


def test_hash_refresh_token_never_returns_the_plaintext() -> None:
    token = generate_refresh_token()

    assert hash_refresh_token(token) != token
