from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

_DIGITS_ONLY = re.compile(r"\D+")


def _normalize_phone_input(value: str) -> str:
    digits = _DIGITS_ONLY.sub("", value or "")
    if not digits:
        raise ValueError("Phone number is required.")
    if len(digits) < 10 or len(digits) > 15:
        raise ValueError("Phone number must contain between 10 and 15 digits.")
    return digits


def _normalize_text_input(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("Text is required.")
    return normalized


class SendWhatsAppTextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: int = Field(gt=0)
    booking_id: int = Field(gt=0)
