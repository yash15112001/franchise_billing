"""HTTP response shapes for invoice APIs."""

from __future__ import annotations

from domains.bookings.infrastructure.models import Booking
from domains.bookings.interfaces.serializers import serialize_invoice_detail_for_history
from domains.invoicing.infrastructure.models import Invoice
from domains.payments.infrastructure.models import Payment


def serialize_invoice_payment_create_response(
    *,
    payment: Payment,
    invoice: Invoice,
) -> dict:
    """``POST /invoices/{invoice_id}/payments`` — contract: payment_id, invoice_id, updated_at."""

    return {
        "payment_id": payment.id,
        "invoice_id": invoice.id,
        "updated_at": str(invoice.updated_at) if invoice.updated_at is not None else None,
    }


def serialize_invoice_list_row(invoice: Invoice) -> dict:
    """Minimal row for ``GET /invoices``."""

    return {
        "id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "franchise_id": invoice.franchise_id,
        "booking_id": invoice.booking_id,
        "total_payable_amount": str(invoice.total_payable_amount),
        "total_paid_amount": str(invoice.total_paid_amount),
        "payment_status": invoice.payment_status.value,
    }


def serialize_payment_row(payment: Payment) -> dict:
    """Minimal payment row (aligned with payment list contract)."""

    return {
        "id": payment.id,
        "invoice_id": payment.invoice_id,
        "amount": str(payment.amount),
        "mode": payment.mode.value,
        "verified_by": payment.verified_by,
        "reference_number": payment.reference_number,
    }


def serialize_basic_booking(booking: Booking) -> dict:
    """Booking scalars only (no customer, vehicle, or nested relations)."""

    return {
        "id": booking.id,
        "franchise_id": booking.franchise_id,
        "customer_id": booking.customer_id,
        "vehicle_id": booking.vehicle_id,
        "requested_at": booking.requested_at.isoformat(),
        "service_status": booking.service_status.value,
        "created_by": booking.created_by,
        "notes": booking.notes,
        "created_at": booking.created_at.isoformat(),
        "updated_at": booking.updated_at.isoformat(),
    }


def serialize_invoice_detail_response(
    *,
    invoice: Invoice,
    booking: Booking,
    payments: list[Payment],
) -> dict:
    """``GET /invoices/{id}``: one ``invoice`` object with scalars, payments, basic_booking."""

    base = serialize_invoice_detail_for_history(invoice) or {}
    return {
        **base,
        "payments": [serialize_payment_row(p) for p in payments],
        "booking_info": serialize_basic_booking(booking),
    }
