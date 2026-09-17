import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# Argon2id (argon2-cffi's default profile) per spec Section 5/19.
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def generate_refresh_token() -> str:
    """256 bits of randomness, URL-safe — unguessable regardless of hash
    speed, unlike a user-chosen password."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """SHA-256, not Argon2id: this hashes a high-entropy random token, not
    a low-entropy user password, so there is nothing for a slow hash to
    protect against here — only a fast, deterministic lookup is needed."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
