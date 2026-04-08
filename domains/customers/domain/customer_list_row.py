"""Read-model for customer list/get API rows (entity + aggregates)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from domains.customers.infrastructure.models import Customer


@dataclass(frozen=True)
class CustomerListRow:
    """Customer entity with list-only fields attached on the same object."""

    customer: Customer
    last_visit_time: Any | None
    total_visits: int
    total_spending: Decimal
