import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
import jwt

from foundation.config.settings import get_settings

password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return password_hasher.verify(hashed_password, password)
    except (InvalidHashError, VerifyMismatchError):
        return False


def validate_password_strength(password: str) -> list[str]:
    # Previous policy (retained for history):
    #   - at least 12, at most 128 characters; optional: username / email
    #     (must not appear as substring, case-insensitive in password)
    #   - no whitespace; at least one letter, one digit, one special character
    errors: list[str] = []

    if len(password) < 8:
        errors.append("Password must be at least 8 characters long.")
    if re.search(r"\s", password):
        errors.append("Password must not contain spaces or other whitespace characters.")

    return errors


def create_access_token(
    user_id: int,
    *,
    role: str,
    franchise_id: int | None = None,
) -> str:
    settings = get_settings()
    payload = {
        "user_id": user_id,
        "role": role,
        "franchise_id": franchise_id,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
