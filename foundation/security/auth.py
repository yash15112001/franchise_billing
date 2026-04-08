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


def validate_password_strength(
    password: str,
    *,
    username: str | None = None,
    email: str | None = None,
) -> list[str]:
    errors: list[str] = []

    if len(password) < 12:
        errors.append("Password must be at least 12 characters long.")
    if len(password) > 128:
        errors.append("Password must be at most 128 characters long.")
    if re.search(r"\s", password):
        errors.append("Password must not contain spaces or other whitespace characters.")
    if not re.search(r"[A-Za-z]", password):
        errors.append("Password must include at least one alphabetic character.")
    if not re.search(r"\d", password):
        errors.append("Password must include at least one numeric digit.")
    if not re.search(r"[^A-Za-z0-9]", password):
        errors.append("Password must include at least one special character.")

    lowered_password = password.lower()
    if username and username.lower() in lowered_password:
        errors.append("Password must not contain the username.")
    if email:
        local_part = email.split("@", 1)[0].lower()
        if local_part and local_part in lowered_password:
            errors.append("Password must not contain the email identifier.")

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
