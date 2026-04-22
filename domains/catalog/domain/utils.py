"""Normalization for catalog ``Service`` text fields (``schema_design``).

``name``, ``vehicle_type``, ``service_category``, and ``description`` are case-insensitive:
strip, store lowercase. Optional ``description`` becomes ``None`` when empty after strip.
"""

from __future__ import annotations

MAX_SERVICE_NAME_LEN = 120
MAX_VEHICLE_TYPE_LEN = 50
MAX_SERVICE_CATEGORY_LEN = 60


def normalize_service_name(value: str) -> str:
    s = value.strip().lower()
    if not s:
        raise ValueError("name cannot be empty or whitespace only.")
    if len(s) > MAX_SERVICE_NAME_LEN:
        raise ValueError(
            f"name must be at most {MAX_SERVICE_NAME_LEN} characters.", )
    return s


def normalize_service_vehicle_type(value: str) -> str:
    s = value.strip().lower()
    if not s:
        raise ValueError("vehicle_type cannot be empty or whitespace only.")
    if len(s) > MAX_VEHICLE_TYPE_LEN:
        raise ValueError(
            f"vehicle_type must be at most {MAX_VEHICLE_TYPE_LEN} characters.",
        )
    return s


def normalize_service_category(value: str) -> str:
    s = value.strip().lower()
    if not s:
        raise ValueError(
            "service_category cannot be empty or whitespace only.")
    if len(s) > MAX_SERVICE_CATEGORY_LEN:
        raise ValueError(
            "service_category must be at most "
            f"{MAX_SERVICE_CATEGORY_LEN} characters.", )
    return s


def normalize_service_description(value: str | None) -> str | None:
    if value is None:
        return None
    s = value.strip()
    return s if s else None
