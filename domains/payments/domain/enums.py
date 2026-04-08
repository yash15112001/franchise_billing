"""Payment domain enumerations (see ``schema_design`` Payment.mode)."""

from __future__ import annotations

from enum import StrEnum


class PaymentMode(StrEnum):
    CASH = "cash"
    CHEQUE = "cheque"
    CARD = "card"
    UPI = "upi"
    BANK_TRANSFER = "bank_transfer"
    OTHER = "other"
