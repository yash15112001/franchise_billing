from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_required_text(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("Value must not be blank.")
    return normalized


def _normalize_inventory_item_name(value: str) -> str:
    return _normalize_required_text(value).lower()


class InventoryItemResponse(BaseModel):
    id: int
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class InventoryItemCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _normalize_inventory_item_name(value)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class InventoryItemPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_inventory_item_name(value)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class UpdateOnlyResponse(BaseModel):
    id: int
    updated_at: datetime


class SoftDeleteResponse(BaseModel):
    id: int
    is_deleted: bool
    updated_at: datetime


class ServiceInventoryItemUsageResponse(BaseModel):
    id: int
    inventory_item_id: int
    service_id: int
    quantity_required: Decimal
    created_at: datetime
    updated_at: datetime


class ServiceInventoryItemUsageCreateRequest(BaseModel):
    service_id: int = Field(gt=0)
    inventory_item_id: int = Field(gt=0)
    quantity_required: Decimal = Field(gt=0, decimal_places=4)


class ServiceInventoryItemUsagePatchRequest(BaseModel):
    quantity_required: Decimal = Field(gt=0, decimal_places=4)


class FranchiseInventoryResponse(BaseModel):
    id: int
    franchise_id: int
    inventory_item_id: int
    quantity: Decimal
    created_at: datetime
    updated_at: datetime


class AddFranchiseInventoryStockRequest(BaseModel):
    quantity_to_be_added: Decimal = Field(gt=0, decimal_places=4)


class SetFranchiseInventoryStockRequest(BaseModel):
    quantity: Decimal = Field(ge=0, decimal_places=4)
