from __future__ import annotations

from datetime import time
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator

from domains.franchises.domain.utils import (
    normalize_case_insensitive_text,
    normalize_franchise_name,
    normalize_optional_text,
    normalize_gstin,
    normalize_indian_pincode,
    normalize_location_url,
    normalize_pan,
)


class CreateFranchiseRequest(BaseModel):
    """POST /franchises — body per api_contracts (code is generated server-side in final flow)."""

    name: str = Field(min_length=1, max_length=120)
    address: str = Field(min_length=1, max_length=255)
    city: str = Field(min_length=1, max_length=80)
    state: str = Field(min_length=1, max_length=80)
    pincode: str = Field(min_length=6, max_length=6)
    country: str = Field(min_length=1, max_length=80)
    location_url: str | None = Field(default=None, max_length=512)
    gst_number: str = Field(min_length=15, max_length=15)
    pan_number: str = Field(min_length=10, max_length=10)
    monthly_target: Decimal | None = None
    description: str | None = None

    @field_validator("name")
    @classmethod
    def name_trim_preserve_case(cls, v: str) -> str:
        return normalize_franchise_name(v)

    @field_validator("address", "city", "state", "country")
    @classmethod
    def address_fields_lowercase(cls, v: str) -> str:
        return normalize_case_insensitive_text(v)

    @field_validator("description")
    @classmethod
    def description_optional_preserve_case(cls, v: str | None) -> str | None:
        return normalize_optional_text(v)

    @field_validator("pincode")
    @classmethod
    def pincode_india(cls, v: str) -> str:
        return normalize_indian_pincode(v)

    @field_validator("pan_number")
    @classmethod
    def pan_india(cls, v: str) -> str:
        return normalize_pan(v)

    @field_validator("gst_number")
    @classmethod
    def gstin_india(cls, v: str) -> str:
        return normalize_gstin(v)

    @field_validator("location_url")
    @classmethod
    def location_url_http(cls, v: str | None) -> str | None:
        return normalize_location_url(v)

    # TODO : confirm weather this will be the case for franchise, then uncomment/remove this section
    # @model_validator(mode="after")
    # def gstin_must_embed_pan(self) -> Self:
    #     if self.gst_number[2:12] != self.pan_number:
    #         raise ValueError(
    #             "GSTIN must embed the same PAN as pan_number (PAN is characters 3–12 of GSTIN).",
    #         )
    #     return self


class UpdateFranchiseRequest(BaseModel):
    """PATCH /franchises/{franchise_id} — partial update."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    address: str | None = Field(default=None, min_length=1, max_length=255)
    city: str | None = Field(default=None, min_length=1, max_length=80)
    state: str | None = Field(default=None, min_length=1, max_length=80)
    pincode: str | None = Field(default=None, min_length=6, max_length=6)
    country: str | None = Field(default=None, min_length=1, max_length=80)
    gst_number: str | None = Field(default=None, min_length=15, max_length=15)
    pan_number: str | None = Field(default=None, min_length=10, max_length=10)
    monthly_target: Decimal | None = None
    location_url: str | None = Field(default=None, max_length=512)
    description: str | None = None

    @field_validator("name")
    @classmethod
    def name_trim_preserve_case(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return normalize_franchise_name(v)

    @field_validator("address", "city", "state", "country")
    @classmethod
    def address_fields_lowercase(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return normalize_case_insensitive_text(v)

    @field_validator("description")
    @classmethod
    def description_optional_preserve_case(cls, v: str | None) -> str | None:
        return normalize_optional_text(v)

    @field_validator("pincode")
    @classmethod
    def pincode_india(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return normalize_indian_pincode(v)

    @field_validator("pan_number")
    @classmethod
    def pan_india(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return normalize_pan(v)

    @field_validator("gst_number")
    @classmethod
    def gstin_india(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return normalize_gstin(v)

    @field_validator("location_url")
    @classmethod
    def location_url_http(cls, v: str | None) -> str | None:
        return normalize_location_url(v)

    # TODO : confirm weather this will be the case for franchise, then uncomment/remove this section
    # @model_validator(mode="after")
    # def gstin_must_embed_pan_when_both_set(self) -> Self:
    #     if self.gst_number is None or self.pan_number is None:
    #         return self
    #     if self.gst_number[2:12] != self.pan_number:
    #         raise ValueError(
    #             "GSTIN must embed the same PAN as pan_number (PAN is characters 3–12 of GSTIN).",
    #         )
    #     return self


class CreateCommissionPolicyRequest(BaseModel):
    """POST /franchises/{franchise_id}/commission-policies — contract field name."""

    commission_percentage: Decimal = Field(gt=0, le=100)


class PatchFranchiseTimingRequest(BaseModel):
    """PATCH /franchises/{franchise_id}/timings/{day_of_week}

    ``is_closed`` is required every time. When true, ``open_time`` / ``close_time`` in the
    body are ignored (the server clears stored times). When false, both times are required
    and open must be strictly before close.
    """

    open_time: time | None = None
    close_time: time | None = None
    is_closed: bool

    @model_validator(mode="after")
    def times_match_closed_flag(self) -> Self:
        if self.is_closed:
            return self
        if self.open_time is None or self.close_time is None:
            raise ValueError(
                "open_time and close_time are required when is_closed is false.",
            )
        if self.open_time >= self.close_time:
            raise ValueError(
                "When is_closed is false, open_time must be strictly before close_time.",
            )
        return self


class CreateFranchiseReviewRequest(BaseModel):
    """POST /franchises/{franchise_id}/reviews"""

    customer_id: int = Field(gt=0)
    rating: Decimal = Field(gt=0, le=5)
    comment: str | None = None

    @field_validator("comment")
    @classmethod
    def comment_optional_preserve_case(cls, v: str | None) -> str | None:
        return normalize_optional_text(v)


class PatchFranchiseReviewRequest(BaseModel):
    """PATCH /franchises/{franchise_id}/reviews/{review_id}"""

    rating: Decimal | None = Field(default=None, gt=0, le=5)
    comment: str | None = None

    @field_validator("comment")
    @classmethod
    def comment_optional_preserve_case(cls, v: str | None) -> str | None:
        return normalize_optional_text(v)
