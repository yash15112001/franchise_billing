"""HTTP request bodies for payment APIs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PatchPaymentReferenceRequest(BaseModel):
    """``PATCH /payments/{payment_id}`` — only ``reference_number`` may change."""

    reference_number: str | None = Field(default=None, max_length=120)
