"""Booking domain enumerations (see ``schema_design`` Booking.service_status)."""

from __future__ import annotations

from enum import StrEnum


class BookingServiceStatus(StrEnum):
    PENDING = "pending"
    ONGOING = "ongoing"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
