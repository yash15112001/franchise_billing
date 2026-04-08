"""Invoice application services.

Implement domain logic here. HTTP contracts:
``docs/architecture/api_contracts.txt`` (Invoice).
"""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from domains.audit.application.service import write_audit_log
from domains.bookings.application.service import _query_bookings
from domains.bookings.infrastructure.models import Booking
from domains.franchises.application.service import get_franchise_for_actor
from domains.invoicing.domain.enums import InvoicePaymentStatus
from domains.invoicing.infrastructure.models import Invoice
from domains.payments.domain.enums import PaymentMode
from domains.payments.infrastructure.models import Payment
from domains.users.domain.access import UserRole
from domains.users.infrastructure.models import User
from foundation.errors import AppError

logger = logging.getLogger(__name__)

_MONEY_QUANT = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)


def _query_invoices(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    franchise_id: int | None = None,
    invoice_number: str | None = None,
    booking_id: int | None = None,
    gst_included: bool | None = None,
    payment_status: InvoicePaymentStatus | None = None,
    invoice_id: int | None = None,
    order_desc_by_created: bool = True,
) -> list[Invoice]:
    """Filter invoices visible to the actor; shared by list and single-invoice fetch."""

    if actor_role is UserRole.MAIN_ADMIN:
        if franchise_id is not None:
            get_franchise_for_actor(
                db,
                actor_role=actor_role,
                actor_franchise_id=actor_franchise_id,
                franchise_id=franchise_id,
            )
    else:
        if actor_franchise_id is None:
            raise AppError(
                status_code=status.HTTP_403_FORBIDDEN,
                message="Franchise context is required.",
                error_code="MISSING_FRANCHISE_CONTEXT",
                details={},
            )
        if franchise_id is not None and franchise_id != actor_franchise_id:
            logger.info(
                "Ignored franchise_id for invoice query; "
                "franchise users only see their franchise. "
                "actor_user_id=%s requested_franchise_id=%s actor_franchise_id=%s",
                actor.id,
                franchise_id,
                actor_franchise_id,
            )

    statement = select(Invoice)
    if order_desc_by_created:
        statement = statement.order_by(Invoice.created_at.desc())

    if actor_role is UserRole.MAIN_ADMIN:
        if franchise_id is not None:
            statement = statement.where(Invoice.franchise_id == franchise_id)
    else:
        statement = statement.where(Invoice.franchise_id == actor_franchise_id)

    if invoice_number is not None:
        statement = statement.where(Invoice.invoice_number == invoice_number)
    if booking_id is not None:
        statement = statement.where(Invoice.booking_id == booking_id)
    if gst_included is not None:
        statement = statement.where(Invoice.gst_included == gst_included)
    if payment_status is not None:
        statement = statement.where(Invoice.payment_status == payment_status)
    if invoice_id is not None:
        statement = statement.where(Invoice.id == invoice_id)

    return list(db.scalars(statement).all())


def get_invoice_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    invoice_id: int,
) -> Invoice:
    """Single invoice visible to the actor, or ``INVOICE_NOT_FOUND``."""

    rows = _query_invoices(
        db,
        actor=actor,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        franchise_id=None,
        invoice_number=None,
        booking_id=None,
        gst_included=None,
        payment_status=None,
        invoice_id=invoice_id,
        order_desc_by_created=False,
    )
    if not rows:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Invoice not found.",
            error_code="INVOICE_NOT_FOUND",
            details={"invoice_id": invoice_id},
        )
    return rows[0]


def list_invoices_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    franchise_id: int | None,
    invoice_number: str | None,
    booking_id: int | None,
    gst_included: bool | None,
    payment_status: InvoicePaymentStatus | None,
) -> list[Invoice]:
    """Rows for ``GET /invoices`` (serialization in HTTP layer)."""

    return _query_invoices(
        db,
        actor=actor,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        franchise_id=franchise_id,
        invoice_number=invoice_number,
        booking_id=booking_id,
        gst_included=gst_included,
        payment_status=payment_status,
        invoice_id=None,
        order_desc_by_created=True,
    )


def get_invoice_detail_bundle_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    invoice_id: int,
) -> tuple[Invoice, Booking, list[Payment]]:
    invoice = get_invoice_for_actor(
        db,
        actor=actor,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        invoice_id=invoice_id,
    )

    franchise_filter = (invoice.franchise_id
                        if actor_role is UserRole.MAIN_ADMIN else None)
    bookings = _query_bookings(
        db,
        actor=actor,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        franchise_id=franchise_filter,
        booking_id=invoice.booking_id,
        order_desc_by_created=False,
    )
    if not bookings:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Booking for this invoice was not found.",
            error_code="BOOKING_NOT_FOUND",
            details={"booking_id": invoice.booking_id},
        )

    payment_rows = list(
        db.scalars(
            select(Payment).where(
                Payment.invoice_id == invoice.id).order_by(
                    Payment.created_at.asc())).all())

    return invoice, bookings[0], payment_rows


def create_invoice_payment_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    invoice_id: int,
    amount: Decimal,
    mode: PaymentMode,
    reference_number: str | None,
) -> tuple[Payment, Invoice]:
    """Record a payment; update ``total_paid_amount`` and ``payment_status``."""

    invoice = get_invoice_for_actor(
        db,
        actor=actor,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        invoice_id=invoice_id,
    )

    payable = _money(invoice.total_payable_amount)
    paid_before = _money(invoice.total_paid_amount)
    remaining = _money(payable - paid_before)

    if remaining <= Decimal("0"):
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="This invoice is already fully paid.",
            error_code="INVOICE_ALREADY_FULLY_PAID",
            details={
                "invoice_id": invoice.id,
                "total_payable_amount": str(payable),
                "total_paid_amount": str(paid_before),
            },
        )

    pay_amount = _money(amount)
    if pay_amount <= Decimal("0"):
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Payment amount must be greater than zero.",
            error_code="INVALID_PAYMENT_AMOUNT",
            details={"amount": str(amount)},
        )

    paid_after = _money(paid_before + pay_amount)
    if paid_after > payable:
        excess = _money(paid_after - payable)
        if excess >= Decimal("1"):
            raise AppError(
                status_code=status.HTTP_400_BAD_REQUEST,
                message=(
                    "Overpayment of 1 rupee or more was detected; reduce the "
                    "payment amount."),
                error_code="OVERPAYMENT_EXCEEDS_LIMIT",
                details={
                    "invoice_id": invoice.id,
                    "payable": str(payable),
                    "paid_after": str(paid_after),
                    "excess_over_payable": str(excess),
                },
            )

    complete = paid_after >= payable

    invoice.total_paid_amount = paid_after

    if complete:
        invoice.payment_status = InvoicePaymentStatus.COMPLETE
    elif paid_after > Decimal("0"):
        invoice.payment_status = InvoicePaymentStatus.PARTIAL
    else:
        invoice.payment_status = InvoicePaymentStatus.PENDING

    payment = Payment(
        invoice_id=invoice.id,
        amount=pay_amount,
        mode=mode,
        verified_by=actor.id,
        reference_number=reference_number,
    )
    db.add(payment)
    db.flush()
    db.refresh(invoice)
    db.refresh(payment)

    audit_payload: dict = {
        "invoice_id": invoice.id,
        "amount": str(pay_amount),
        "mode": mode.value,
        "reference_number": reference_number,
        "paid_after": str(paid_after),
        "payable": str(payable),
    }
    if paid_after > payable:
        audit_payload["excess_over_payable"] = str(_money(paid_after - payable))

    write_audit_log(
        db,
        action="invoice.payment.create",
        entity_name="payments",
        entity_id=str(payment.id),
        actor_user_id=actor.id,
        franchise_id=invoice.franchise_id,
        payload=audit_payload,
    )

    return payment, invoice
