"""HTTP request bodies for bookings (see ``api_contracts.txt`` — Booking)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from domains.bookings.domain.enums import BookingServiceStatus


class RequestedService(BaseModel):
    """One requested catalog service line for a booking (service + quantity)."""

    service_id: int = Field(gt=0)
    qty: int = Field(ge=1)


class CreateBookingRequest(BaseModel):
    """Create booking using existing franchise, customer, vehicle, and services (seed data).

    This version does **not** support ``customer_info`` / ``vehicle_info`` (inline resource
    creation); send ``customer_id`` and ``vehicle_id`` only.
    """

    franchise_id: int | None = None
    customer_id: int
    vehicle_id: int
    requested_at: datetime
    notes: str | None = Field(default=None, max_length=10_000)
    requested_services: list[RequestedService] = Field(
        ...,
        min_length=1,
        description=
        "Requested services: at least one entry; duplicate service_id is not allowed.",
    )
    gst_included: bool = True

    @model_validator(mode="after")
    def _unique_service_ids(self) -> CreateBookingRequest:
        seen: set[int] = set()
        for line in self.requested_services:
            if line.service_id in seen:
                raise ValueError(
                    f"Duplicate service_id in requested_services: {line.service_id}."
                )
            seen.add(line.service_id)
        return self


class CreateBookingItemRequest(BaseModel):
    """Set ``qty`` for ``service_id`` on ``booking_id`` (insert line or replace qty if present)."""

    booking_id: int = Field(gt=0)
    service_id: int = Field(gt=0)
    qty: int = Field(ge=1)


class PutBookingItemRequest(BaseModel):
    """Update one booking line (``PUT /booking-items/{{booking_item_id}}``). ``qty`` 0 deletes the line."""

    qty: int = Field(ge=0)


class ReplaceBookingItemsRequest(BaseModel):
    """Full replacement of requested services (``PUT /bookings/{{booking_id}}/items``)."""

    items: list[RequestedService] = Field(
        ...,
        min_length=1,
        description=
        "Desired lines: at least one; duplicate service_id is not allowed.",
    )

    @model_validator(mode="after")
    def _unique_service_ids(self) -> ReplaceBookingItemsRequest:
        seen: set[int] = set()
        for line in self.items:
            if line.service_id in seen:
                raise ValueError(
                    f"Duplicate service_id in items: {line.service_id}.")
            seen.add(line.service_id)
        return self


class PatchBookingRequest(BaseModel):
    """Update booking status and/or notes (``api_contracts`` PATCH /bookings/{{booking_id}})."""

    service_status: BookingServiceStatus | None = None
    notes: str | None = Field(default=None, max_length=10_000)
