"""Request/response models for invoice HTTP (OpenAPI + typing)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from domains.payments.domain.enums import PaymentMode


class InvoiceListRowResponse(BaseModel):
    """One row in ``GET /invoices`` ``data`` array."""

    model_config = ConfigDict(extra="forbid")

    id: int
    invoice_number: str
    franchise_id: int
    booking_id: int
    total_payable_amount: str
    total_paid_amount: str
    payment_status: str


class ListInvoicesSuccessEnvelope(BaseModel):
    """200 body for ``GET /invoices`` — ``data`` is a list."""

    success: bool = True
    message: str
    data: list[InvoiceListRowResponse]


class InvoiceDetailDataWrapper(BaseModel):
    """``data`` for ``GET /invoices/{id}`` — single object with an ``invoice`` key."""

    model_config = ConfigDict(extra="forbid")

    invoice: dict[str, Any] = Field(
        ...,
        description="Invoice fields, plus payments and basic_booking.",
    )


class GetInvoiceSuccessEnvelope(BaseModel):
    """200 body for ``GET /invoices/{invoice_id}`` — ``data`` is an object, not an array."""

    success: bool = True
    message: str
    data: InvoiceDetailDataWrapper


class CreateInvoicePaymentRequest(BaseModel):
    """Body for ``POST /invoices/{invoice_id}/payments`` (see ``api_contracts``)."""

    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(
        ...,
        gt=0,
        description="Amount collected; must not exceed the invoice remaining balance.",
    )
    mode: PaymentMode
    reference_number: str | None = Field(default=None, max_length=120)


class CreateInvoicePaymentData(BaseModel):
    """``data`` for ``POST /invoices/{invoice_id}/payments``."""

    payment_id: int
    invoice_id: int
    updated_at: str | None


class CreateInvoicePaymentSuccessEnvelope(BaseModel):
    """201 body after recording a payment."""

    success: bool = True
    message: str
    data: CreateInvoicePaymentData
