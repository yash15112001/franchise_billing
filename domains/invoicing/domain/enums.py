"""Invoice domain enumerations (see ``schema_design`` Invoice.payment_status)."""

from __future__ import annotations

from enum import StrEnum


class InvoicePaymentStatus(StrEnum):
    PENDING = "pending"
    PARTIAL = "partial"
    COMPLETE = "complete"
