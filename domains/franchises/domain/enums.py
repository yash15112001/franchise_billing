from __future__ import annotations

from enum import StrEnum


class FranchiseStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING_APPROVAL = "pending_approval"


class DayOfWeek(StrEnum):
    SUNDAY = "sunday"
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
