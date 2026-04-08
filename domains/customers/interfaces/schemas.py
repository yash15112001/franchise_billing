from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from domains.customers.domain.utils import (
    MAX_REGISTRATION_LEN,
    MAX_COLOUR_LEN,
    MAX_MODEL_LEN,
    MAX_VEHICLE_TYPE_LEN,
    MAX_VEHICLE_NAME_LEN,
    normalize_full_name,
    normalize_mobile_number,
    normalize_optional_email,
    normalize_optional_vehicle_name,
    normalize_registration_number,
    normalize_vehicle_optional_text,
    normalize_whatsapp_number,
    normalize_colour,
    normalize_model,
    normalize_vehicle_type,
)
from domains.customers.infrastructure.models import CustomerType


class CustomerCreateRequest(BaseModel):
    franchise_id: int | None = None
    full_name: str = Field(min_length=1, max_length=120)
    mobile_number: str = Field(min_length=10, max_length=10)
    whatsapp_number: str = Field(default="", max_length=10)
    email: EmailStr | None = None
    customer_type: CustomerType | None = Field(default=None)

    @model_validator(mode="after")
    def _default_customer_type_when_omitted_or_null(
            self) -> CustomerCreateRequest:
        if self.customer_type is None:
            self.customer_type = CustomerType.NEW
        return self

    @field_validator("full_name")
    @classmethod
    def v_full_name(cls, v: str) -> str:
        return normalize_full_name(v)

    @field_validator("mobile_number")
    @classmethod
    def v_mobile(cls, v: str) -> str:
        return normalize_mobile_number(v)

    @field_validator("whatsapp_number")
    @classmethod
    def v_whatsapp(cls, v: str) -> str:
        return normalize_whatsapp_number(v)

    @field_validator("email", mode="before")
    @classmethod
    def v_email(cls, v: object) -> str | None:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            return normalize_optional_email(v)
        return v


class CustomerPatchRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    email: EmailStr | None = None
    mobile_number: str | None = Field(default=None,
                                      min_length=10,
                                      max_length=10)
    whatsapp_number: str | None = Field(default=None, max_length=10)
    customer_type: CustomerType | None = None

    @field_validator("full_name")
    @classmethod
    def v_full_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return normalize_full_name(v)

    @field_validator("mobile_number")
    @classmethod
    def v_mobile(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return normalize_mobile_number(v)

    @field_validator("whatsapp_number")
    @classmethod
    def v_whatsapp(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return normalize_whatsapp_number(v)

    @field_validator("email", mode="before")
    @classmethod
    def v_email(cls, v: object) -> str | None:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            return normalize_optional_email(v)
        return v


class VehicleCreateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=MAX_VEHICLE_NAME_LEN)
    customer_id: int
    franchise_id: int | None = None
    registration_number: str = Field(min_length=1,
                                     max_length=MAX_REGISTRATION_LEN)
    colour: str = Field(min_length=1, max_length=MAX_COLOUR_LEN)
    model: str = Field(min_length=1, max_length=MAX_MODEL_LEN)
    vehicle_type: str = Field(min_length=1, max_length=MAX_VEHICLE_TYPE_LEN)

    @field_validator("registration_number")
    @classmethod
    def v_reg(cls, v: str) -> str:
        return normalize_registration_number(v)

    @field_validator("colour")
    @classmethod
    def v_colour(cls, v: str) -> str:
        return normalize_colour(v)

    @field_validator("model")
    @classmethod
    def v_model(cls, v: str) -> str:
        return normalize_model(v)

    @field_validator("vehicle_type")
    @classmethod
    def v_vehicle_type(cls, v: str) -> str:
        return normalize_vehicle_type(v)

    @field_validator("name")
    @classmethod
    def v_name(cls, v: str | None) -> str | None:
        return normalize_optional_vehicle_name(v)


class VehiclePatchRequest(BaseModel):
    name: str | None = Field(default=None, max_length=MAX_VEHICLE_NAME_LEN)
    vehicle_type: str | None = Field(default=None,
                                     max_length=MAX_VEHICLE_TYPE_LEN)
    colour: str | None = Field(default=None, max_length=MAX_COLOUR_LEN)
    model: str | None = Field(default=None, max_length=MAX_MODEL_LEN)

    @field_validator("colour")
    @classmethod
    def v_colour(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return normalize_vehicle_optional_text(v) if v else ""

    @field_validator("model")
    @classmethod
    def v_model(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return normalize_vehicle_optional_text(v) if v else ""

    @field_validator("vehicle_type")
    @classmethod
    def v_vehicle_type(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return normalize_vehicle_optional_text(v) if v else ""

    @field_validator("name")
    @classmethod
    def v_name(cls, v: str | None) -> str | None:
        return normalize_optional_vehicle_name(v)
