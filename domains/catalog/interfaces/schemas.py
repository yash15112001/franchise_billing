from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from domains.catalog.domain.utils import (
    normalize_service_category,
    normalize_service_description,
    normalize_service_name,
    normalize_service_vehicle_type,
)


class ServiceResponse(BaseModel):
    id: int
    name: str
    vehicle_type: str
    service_category: str
    base_price: Decimal
    discount_percentage: Decimal
    estimated_duration: time
    description: str | None
    created_at: datetime
    updated_at: datetime


class ServiceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    vehicle_type: str = Field(min_length=1, max_length=50)
    service_category: str = Field(min_length=1, max_length=60)
    discount_percentage: Decimal = Field(ge=0, le=100)
    estimated_duration: time
    base_price: Decimal = Field(gt=0)
    description: str | None = None

    @field_validator("name")
    @classmethod
    def name_lowercase(cls, v: str) -> str:
        return normalize_service_name(v)

    @field_validator("vehicle_type")
    @classmethod
    def vehicle_type_lowercase(cls, v: str) -> str:
        return normalize_service_vehicle_type(v)

    @field_validator("service_category")
    @classmethod
    def service_category_lowercase(cls, v: str) -> str:
        return normalize_service_category(v)

    @field_validator("description")
    @classmethod
    def description_optional(cls, v: str | None) -> str | None:
        return normalize_service_description(v)


class ServicePatchRequest(BaseModel):
    base_price: Decimal | None = Field(default=None, gt=0)
    discount_percentage: Decimal | None = Field(default=None, ge=0, le=100)
    estimated_duration: time | None = None
    description: str | None = None

    @field_validator("description")
    @classmethod
    def description_optional_lowercase(cls, v: str | None) -> str | None:
        return normalize_service_description(v)


class ServiceStatusPatchResponse(BaseModel):
    id: int
    is_active: bool
    updated_at: datetime


class ServicePopularityRow(BaseModel):
    id: int
    popularity_rank: int
    name: str
    vehicle_type: str
    service_category: str
    base_price: Decimal
    discount_percentage: Decimal
    estimated_duration: time
    description: str | None
    created_at: datetime
    updated_at: datetime


class ServiceAnalyticsSummary(BaseModel):
    total_services: int
    average_service_value: Decimal
    highest_earning_service: str | None
    most_booked_service: str | None
