"""Normalization for user text fields (``schema_design``).

``username`` and ``full_name`` are case-sensitive: trim only, preserve casing.
``email`` is optional and case-sensitive: trim; empty / whitespace-only becomes ``None``.
"""

from __future__ import annotations

MAX_USERNAME_LEN = 80
MAX_FULL_NAME_LEN = 120


def normalize_username(value: str) -> str:
    """Trim; reject blank; enforce max length; preserve letter casing."""
    s = value.strip()
    if not s:
        raise ValueError("username cannot be empty or whitespace only.")
    if len(s) > MAX_USERNAME_LEN:
        raise ValueError(
            f"username must be at most {MAX_USERNAME_LEN} characters.",
        )
    return s


def normalize_full_name(value: str) -> str:
    """Trim; reject blank; enforce max length; preserve letter casing."""
    s = value.strip()
    if not s:
        raise ValueError("full_name cannot be empty or whitespace only.")
    if len(s) > MAX_FULL_NAME_LEN:
        raise ValueError(
            f"full_name must be at most {MAX_FULL_NAME_LEN} characters.",
        )
    return s


def normalize_optional_email(value: str | None) -> str | None:
    """Trim optional email; empty or whitespace-only -> ``None``; preserve casing."""
    if value is None:
        return None
    s = value.strip()
    return s if s else None
