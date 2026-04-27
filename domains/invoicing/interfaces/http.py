"""Invoice HTTP (see ``api_contracts.txt``)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from starlette import status as http_status

from domains.invoicing.application.service import (
    create_invoice_payment_for_actor,
    get_invoice_detail_bundle_for_actor,
    list_invoices_for_actor,
    soft_delete_invoice_for_actor,
)
from domains.invoicing.domain.enums import InvoicePaymentStatus
from domains.invoicing.interfaces.schemas import CreateInvoicePaymentRequest
from domains.invoicing.interfaces.serializers import (
    serialize_invoice_detail_response,
    serialize_invoice_list_row,
    serialize_invoice_payment_create_response,
)
from domains.users.domain.access import (
    CREATE_INVOICE_PAYMENTS,
    DELETE_INVOICES,
    MANUAL_UPDATE_INVOICE_PAYMENT_STATUS,
    UPDATE_INVOICE_GST,
    VIEW_INVOICES,
)
from foundation.database.session import get_db
from foundation.errors import AppError
from foundation.web.dependencies import FranchiseScope, UserContext, get_franchise_scope, require_permissions
from foundation.web.responses import error_response, internal_error_response, success_response

router = APIRouter(prefix="/invoices", tags=["invoices"])

# --- /invoices ---


@router.get("")
def list_invoices(
        invoice_number: str | None = Query(default=None),
        franchise_id: int | None = Query(default=None),
        booking_id: int | None = Query(default=None),
        gst_included: bool | None = Query(default=None),
        payment_status: InvoicePaymentStatus | None = Query(default=None),
        context: UserContext = Depends(require_permissions(VIEW_INVOICES)),
        db: Session = Depends(get_db),
) -> JSONResponse:
    """List invoices visible to the actor (franchise-scoped unless main admin).

    **Query:** optional filters — `invoice_number`, `franchise_id` (main admin), `booking_id`,
    `gst_included`, `payment_status` (`InvoicePaymentStatus` enum).

    **Auth:** `VIEW_INVOICES`.

    **Success:** 200 — `data`: array of minimal invoice rows (`serialize_invoice_list_row`).
    **Errors:** AppError (`MISSING_FRANCHISE_CONTEXT`, …); 422 `VALIDATION_ERROR`; 500 `INTERNAL_SERVER_ERROR`.
    """
    try:
        invoices = list_invoices_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            franchise_id=franchise_id,
            invoice_number=invoice_number,
            booking_id=booking_id,
            gst_included=gst_included,
            payment_status=payment_status,
        )
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    else:
        return success_response(
            message="Invoices fetched successfully.",
            data=[serialize_invoice_list_row(inv) for inv in invoices],
            status_code=http_status.HTTP_200_OK,
        )


@router.post("/{invoice_id}/payments")
def create_invoice_payment(
        invoice_id: int,
        payload: CreateInvoicePaymentRequest,
        context: UserContext = Depends(
            require_permissions(CREATE_INVOICE_PAYMENTS)),
        db: Session = Depends(get_db),
) -> JSONResponse:
    """Record a payment against an invoice; updates totals and payment status.

    **Path:** `invoice_id`. **Body:** `CreateInvoicePaymentRequest` — `amount`, `mode`, optional `reference_number`.
    `verified_by` is the authenticated user (not in body).

    **Auth:** `CREATE_INVOICE_PAYMENTS`.

    **Success:** 201 — `data`: `payment_id`, `invoice_id`, `updated_at` (invoice).
    **Errors:** AppError e.g. `INVOICE_NOT_FOUND`, `INVOICE_ALREADY_FULLY_PAID`, `INVALID_PAYMENT_AMOUNT`,
    `OVERPAYMENT_EXCEEDS_LIMIT` (excess ≥ 1 unit over payable). 422 / 500 as usual.
    """
    try:
        payment, invoice = create_invoice_payment_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            invoice_id=invoice_id,
            amount=payload.amount,
            mode=payload.mode,
            reference_number=payload.reference_number,
        )
        db.commit()
    except AppError as exc:
        db.rollback()
        return error_response(exc)
    except Exception:
        db.rollback()
        return internal_error_response()
    else:
        return success_response(
            message="Payment recorded successfully.",
            data=serialize_invoice_payment_create_response(
                payment=payment,
                invoice=invoice,
            ),
            status_code=http_status.HTTP_201_CREATED,
        )


@router.patch("/{invoice_id}/gst", include_in_schema=False)
def patch_invoice_gst(
        invoice_id: int,
        _context: UserContext = Depends(
            require_permissions(UPDATE_INVOICE_GST)),
        _scope: FranchiseScope = Depends(get_franchise_scope),
) -> JSONResponse:
    """Not available in API v1 (GST update). Hidden from OpenAPI."""
    return error_response(
        AppError(
            status_code=http_status.HTTP_501_NOT_IMPLEMENTED,
            message="Updating invoice GST is not available in API v1.",
            error_code="NOT_AVAILABLE_IN_V1",
            details={
                "endpoint": "PATCH /invoices/{invoice_id}/gst",
                "invoice_id": invoice_id,
            },
        ))


@router.patch("/{invoice_id}/manual-payment-status", include_in_schema=False)
def patch_invoice_manual_payment_status(
        invoice_id: int,
        _context: UserContext = Depends(
            require_permissions(MANUAL_UPDATE_INVOICE_PAYMENT_STATUS)),
        _scope: FranchiseScope = Depends(get_franchise_scope),
) -> JSONResponse:
    """Not available in API v1 (manual payment status). Hidden from OpenAPI."""
    return error_response(
        AppError(
            status_code=http_status.HTTP_501_NOT_IMPLEMENTED,
            message=
            "Manual invoice payment status updates are not available in API v1.",
            error_code="NOT_AVAILABLE_IN_V1",
            details={
                "endpoint":
                "PATCH /invoices/{invoice_id}/manual-payment-status",
                "invoice_id": invoice_id,
            },
        ))


@router.get("/{invoice_id}")
def get_invoice(
        invoice_id: int,
        context: UserContext = Depends(require_permissions(VIEW_INVOICES)),
        db: Session = Depends(get_db),
) -> JSONResponse:
    """Single invoice with nested payment list and basic booking info.

    **Path:** `invoice_id`. **Auth:** `VIEW_INVOICES`.

    **Success:** 200 — `data`: invoice fields + `payments` + `booking_info` (see `serialize_invoice_detail_response`).
    **Errors:** `INVOICE_NOT_FOUND`, `BOOKING_NOT_FOUND`, `MISSING_FRANCHISE_CONTEXT`, etc. 422 / 500.
    """
    try:
        invoice, booking, payments = get_invoice_detail_bundle_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            invoice_id=invoice_id,
        )
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    else:
        return success_response(
            message="Invoice fetched successfully.",
            data=serialize_invoice_detail_response(
                invoice=invoice,
                booking=booking,
                payments=payments,
            ),
            status_code=http_status.HTTP_200_OK,
        )


@router.delete("/{invoice_id}")
def delete_invoice(
        invoice_id: int,
        context: UserContext = Depends(require_permissions(DELETE_INVOICES)),
        db: Session = Depends(get_db),
) -> JSONResponse:
    """Soft-delete an invoice by deleting its booking tree (booking exception rule)."""
    try:
        invoice, booking = soft_delete_invoice_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            invoice_id=invoice_id,
        )
        db.commit()
    except AppError as exc:
        db.rollback()
        return error_response(exc)
    except Exception:
        db.rollback()
        return internal_error_response()
    else:
        return success_response(
            message="Invoice deleted successfully.",
            data={
                "id": invoice.id,
                "booking_id": booking.id,
                "is_deleted": invoice.is_deleted,
                "updated_at": str(invoice.updated_at),
            },
            status_code=http_status.HTTP_200_OK,
        )
