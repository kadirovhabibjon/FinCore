from app.core.security import hash_password, verify_password


def test_hash_password_does_not_return_plaintext() -> None:
    hashed = hash_password("correct horse battery staple")

    assert hashed != "correct horse battery staple"
    assert hashed.startswith("$argon2id$")


def test_verify_password_accepts_the_correct_password() -> None:
    hashed = hash_password("correct horse battery staple")

    assert verify_password("correct horse battery staple", hashed) is True


def test_verify_password_rejects_the_wrong_password() -> None:
    hashed = hash_password("correct horse battery staple")

    assert verify_password("wrong password", hashed) is False


def test_two_hashes_of_the_same_password_differ() -> None:
    # Argon2 salts each hash independently, so equal passwords never
    # produce equal hashes — a stolen hash table can't be joined against
    # itself to find repeated passwords.
    first = hash_password("correct horse battery staple")
    second = hash_password("correct horse battery staple")

    assert first != second
