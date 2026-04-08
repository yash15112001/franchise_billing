"""Payment application services.

Implement domain logic here. HTTP contracts:
``docs/architecture/api_contracts.txt`` (Payment).
"""

from __future__ import annotations

import logging

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from domains.audit.application.service import write_audit_log
from domains.franchises.application.service import get_franchise_for_actor
from domains.invoicing.infrastructure.models import Invoice
from domains.payments.domain.enums import PaymentMode
from domains.payments.infrastructure.models import Payment
from domains.users.domain.access import UserRole
from domains.users.infrastructure.models import User
from foundation.errors import AppError

logger = logging.getLogger(__name__)


def _query_payments(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    franchise_id: int | None = None,
    invoice_id: int | None = None,
    mode: PaymentMode | None = None,
    verified_by: int | None = None,
    payment_id: int | None = None,
    order_desc_by_created: bool = True,
) -> list[Payment]:
    """Payments visible to the actor (via invoice franchise); shared by list and get."""

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
                "Ignored franchise_id for payment query; "
                "franchise users only see their franchise. "
                "actor_user_id=%s requested_franchise_id=%s actor_franchise_id=%s",
                actor.id,
                franchise_id,
                actor_franchise_id,
            )

    statement = select(Payment).join(
        Invoice,
        Invoice.id == Payment.invoice_id,
    )
    if order_desc_by_created:
        statement = statement.order_by(Payment.created_at.desc())

    if actor_role is UserRole.MAIN_ADMIN:
        if franchise_id is not None:
            statement = statement.where(Invoice.franchise_id == franchise_id)
    else:
        statement = statement.where(Invoice.franchise_id == actor_franchise_id)

    if invoice_id is not None:
        statement = statement.where(Payment.invoice_id == invoice_id)
    if mode is not None:
        statement = statement.where(Payment.mode == mode)
    if verified_by is not None:
        statement = statement.where(Payment.verified_by == verified_by)
    if payment_id is not None:
        statement = statement.where(Payment.id == payment_id)

    return list(db.scalars(statement).all())


def list_payments_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    invoice_id: int | None,
    mode: PaymentMode | None,
    verified_by: int | None,
) -> list[Payment]:
    """Rows for ``GET /payments`` (serialization in HTTP layer)."""

    return _query_payments(
        db,
        actor=actor,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        franchise_id=None,
        invoice_id=invoice_id,
        mode=mode,
        verified_by=verified_by,
        payment_id=None,
        order_desc_by_created=True,
    )


def get_payment_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    payment_id: int,
) -> Payment:
    """Single payment for ``GET /payments/{payment_id}`` (serialization in HTTP layer)."""

    rows = _query_payments(
        db,
        actor=actor,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        franchise_id=None,
        invoice_id=None,
        mode=None,
        verified_by=None,
        payment_id=payment_id,
        order_desc_by_created=False,
    )
    if not rows:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Payment not found.",
            error_code="PAYMENT_NOT_FOUND",
            details={"payment_id": payment_id},
        )
    return rows[0]


def get_payment_detail_bundle_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    payment_id: int,
) -> tuple[Payment, Invoice, User | None]:
    """Payment plus invoice and verifier user for detail response."""

    payment = get_payment_for_actor(
        db,
        actor=actor,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        payment_id=payment_id,
    )
    invoice = db.get(Invoice, payment.invoice_id)
    if invoice is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Invoice for this payment was not found.",
            error_code="INVOICE_NOT_FOUND",
            details={"invoice_id": payment.invoice_id},
        )
    verifier = db.get(User, payment.verified_by)
    return payment, invoice, verifier


def patch_payment_reference_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    payment_id: int,
    reference_number: str | None,
) -> Payment:
    """Update ``reference_number`` only (serialization in HTTP layer)."""

    payment = get_payment_for_actor(
        db,
        actor=actor,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        payment_id=payment_id,
    )

    invoice = db.get(Invoice, payment.invoice_id)
    franchise_id = invoice.franchise_id if invoice is not None else None

    payment.reference_number = reference_number
    db.flush()
    db.refresh(payment)

    write_audit_log(
        db,
        action="payment.reference_update",
        entity_name="payments",
        entity_id=str(payment.id),
        actor_user_id=actor.id,
        franchise_id=franchise_id,
        payload={
            "invoice_id": payment.invoice_id,
            "reference_number": reference_number,
        },
    )

    return payment
