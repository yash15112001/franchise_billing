"""HTTP response shapes for payment APIs."""

from __future__ import annotations

from domains.bookings.interfaces.serializers import serialize_invoice_detail_for_history
from domains.invoicing.infrastructure.models import Invoice
from domains.payments.infrastructure.models import Payment
from domains.users.application.service import serialize_user_summary
from domains.users.infrastructure.models import User


def serialize_payment_list_row(payment: Payment) -> dict:
    """Minimal row for ``GET /payments`` (see ``api_contracts``)."""

    return {
        "id": payment.id,
        "invoice_id": payment.invoice_id,
        "amount": str(payment.amount),
        "mode": payment.mode.value,
        "verified_by": payment.verified_by,
        "reference_number": payment.reference_number,
    }


def serialize_payment_patch_response(payment: Payment) -> dict:
    """``PATCH /payments/{payment_id}`` — ``id``, ``updated_at``."""

    return {
        "id": payment.id,
        "updated_at": str(payment.updated_at) if payment.updated_at is not None else None,
    }


def serialize_payment_detail(
    *,
    payment: Payment,
    invoice: Invoice,
    verifier: User | None,
) -> dict:
    """Full nested payment for ``GET /payments/{payment_id}``."""

    return {
        "id": payment.id,
        "invoice_id": payment.invoice_id,
        "amount": str(payment.amount),
        "mode": payment.mode.value,
        "verified_by": payment.verified_by,
        "reference_number": payment.reference_number,
        "invoice": serialize_invoice_detail_for_history(invoice),
        "verified_by_user":
        serialize_user_summary(verifier) if verifier is not None else {
            "id": payment.verified_by
        },
        "created_at": str(payment.created_at),
        "updated_at": str(payment.updated_at),
    }
