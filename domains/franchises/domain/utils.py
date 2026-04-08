"""Validation helpers for common Indian identifiers used on franchise records.

PIN code: six digits; first digit 1–9 (India Post — no leading zero).
PAN: ten chars, format AAAAA9999A (five letters, four digits, one letter).
GSTIN: fifteen chars — 2-digit state code + PAN (10) + entity code + literal Z + check character.

location_url: optional http(s) URL (validated via Pydantic :class:`~pydantic.HttpUrl`).

Franchise text fields (``schema_design``): ``name`` / ``description`` / ``location_url`` are
case-sensitive (trim only; preserve casing). ``address``, ``city``, ``state``, ``country`` are
case-insensitive (strip, store lowercase). ``gst_number`` / ``pan_number`` are normalized to
uppercase (see :func:`normalize_gstin` / :func:`normalize_pan`).
"""

from __future__ import annotations

import re

from pydantic import HttpUrl, TypeAdapter

_LOCATION_URL_ADAPTER = TypeAdapter(HttpUrl)

# India Post: 6 digits, first digit 1–9
INDIAN_PINCODE_RE = re.compile(r"^[1-9][0-9]{5}$")

# Income Tax: 5 letters + 4 digits + 1 letter (A–Z); typically stored uppercase
PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")

# CBIC-style structural check (format); does not verify checksum digit against PAN
GSTIN_RE = re.compile(
    r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$", )


def normalize_indian_pincode(value: str) -> str:
    v = value.strip()
    if not INDIAN_PINCODE_RE.match(v):
        raise ValueError(
            "pincode must be 6 digits (India), first digit cannot be 0.", )
    return v


def normalize_pan(value: str) -> str:
    v = value.strip().upper()
    if not PAN_RE.match(v):
        raise ValueError(
            "pan_number must be a valid Indian PAN (format: AAAAA9999A).", )
    return v


def normalize_gstin(value: str) -> str:
    v = value.strip().upper()
    if not GSTIN_RE.match(v):
        raise ValueError(
            "gst_number must be a valid 15-character Indian GSTIN "
            "(state code + PAN + entity + Z + check character).", )
    return v


def normalize_location_url(value: str | None) -> str | None:
    """Return ``None`` if missing/blank; otherwise a normalized http(s) URL string."""
    if value is None:
        return None
    s = value.strip()
    if not s:
        return None
    try:
        return str(_LOCATION_URL_ADAPTER.validate_python(s))
    except Exception:
        raise ValueError(
            "location_url must be a valid http or https URL.", ) from None


def normalize_franchise_name(value: str) -> str:
    """Case-sensitive franchise name: trim only; reject blank."""
    s = value.strip()
    if not s:
        raise ValueError("name cannot be empty or whitespace only.")
    return s


def normalize_optional_text(value: str | None) -> str | None:
    """Optional string: trim; preserve casing; empty or whitespace-only -> ``None``.

    Use for case-sensitive optional fields (e.g. franchise ``description``, review ``comment``).
    """
    if value is None:
        return None
    s = value.strip()
    return s if s else None


def normalize_case_insensitive_text(value: str) -> str:
    """Address / city / state / country: strip and lowercase; reject blank after strip."""
    s = value.strip().lower()
    if not s:
        raise ValueError("field cannot be empty or whitespace only.")
    return s
