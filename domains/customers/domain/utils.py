"""Normalization for customer/vehicle text fields (``schema_design``)."""

from __future__ import annotations

MAX_FULL_NAME_LEN = 50
MAX_EMAIL_LEN = 320
# Indian registration mark: post-1989 format is at most 2+2+3+4 alphanumerics (11) without
# separators; typical display with spaces is up to ~14; BH/diplomatic edge cases vary—15 is a
# practical ceiling for storage validation (see schema_design / Wikipedia).
MAX_REGISTRATION_LEN = 15
MAX_COLOUR_LEN = 15
MAX_MODEL_LEN = 20
MAX_VEHICLE_TYPE_LEN = 20
MAX_VEHICLE_NAME_LEN = 120


def normalize_full_name(value: str) -> str:
    s = value.strip()
    if not s:
        raise ValueError("full_name cannot be empty or whitespace only.")
    if len(s) > MAX_FULL_NAME_LEN:
        raise ValueError(
            f"full_name must be at most {MAX_FULL_NAME_LEN} characters.", )
    return s


def normalize_mobile_number(value: str) -> str:
    """Exactly 10 digits; no country code or extra formatting."""
    s = value.strip()
    if not s:
        raise ValueError("cannot be empty or whitespace only.")
    if len(s) != 10 or not s.isdigit():
        raise ValueError("must be exactly 10 digits.")
    return s


def normalize_whatsapp_number(value: str) -> str:
    """Empty means unset; if provided, exactly 10 digits like mobile."""
    s = value.strip()
    if not s:
        return ""
    if len(s) != 10 or not s.isdigit():
        raise ValueError("must be exactly 10 digits.")
    return s


def normalize_optional_email(value: str | None) -> str | None:
    if value is None:
        return None
    s = value.strip()
    if not s:
        return None
    if len(s) > MAX_EMAIL_LEN:
        raise ValueError(f"email must be at most {MAX_EMAIL_LEN} characters.")
    return s


def normalize_registration_number(value: str) -> str:
    """Indian vehicle registration plate (RC number plate), stored uppercase.

    There is no single regex for all states (formats vary). Validation here is
    length + normalization only; stricter patterns can be added per product rules.
    """
    s = value.strip().upper()
    if not s:
        raise ValueError(
            "registration_number cannot be empty or whitespace only.")
    if len(s) > MAX_REGISTRATION_LEN:
        raise ValueError(
            f"registration_number must be at most {MAX_REGISTRATION_LEN} characters.",
        )
    return s


def normalize_colour(value: str) -> str:
    s = value.strip().lower()
    if not s:
        raise ValueError("colour cannot be empty or whitespace only.")
    if len(s) > MAX_COLOUR_LEN:
        raise ValueError(
            f"colour must be at most {MAX_COLOUR_LEN} characters.", )
    return s


def normalize_model(value: str) -> str:
    s = value.strip().lower()
    if not s:
        raise ValueError("model cannot be empty or whitespace only.")
    if len(s) > MAX_COLOUR_LEN:
        raise ValueError(
            f"model must be at most {MAX_COLOUR_LEN} characters.", )
    return s


def normalize_vehicle_type(value: str) -> str:
    s = value.strip().lower()
    if not s:
        raise ValueError("vehicle type cannot be empty or whitespace only.")
    if len(s) > MAX_COLOUR_LEN:
        raise ValueError(
            f"vehicle type must be at most {MAX_COLOUR_LEN} characters.", )
    return s


def normalize_vehicle_optional_text(value: str | None) -> str:
    """Lowercase for color, model, vehicle_type when persisted (schema)."""
    if value is None:
        return ""
    return value.strip().lower()


def normalize_optional_vehicle_name(value: str | None) -> str | None:
    if value is None:
        return None
    s = value.strip()
    if not s:
        return None
    if len(s) > MAX_VEHICLE_NAME_LEN:
        raise ValueError(
            f"vehicle name must be at most {MAX_VEHICLE_NAME_LEN} characters.",
        )
    return s
