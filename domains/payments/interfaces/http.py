"""Payment HTTP (see ``api_contracts.txt``)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from starlette import status as http_status

from domains.payments.application.service import (
    get_payment_detail_bundle_for_actor,
    list_payments_for_actor,
    patch_payment_reference_for_actor,
)
from domains.payments.domain.enums import PaymentMode
from domains.payments.interfaces.schemas import PatchPaymentReferenceRequest
from domains.payments.interfaces.serializers import (
    serialize_payment_detail,
    serialize_payment_list_row,
    serialize_payment_patch_response,
)
from domains.users.domain.access import (
    RECORD_PAYMENT,
    UPDATE_PAYMENT_REFERENCE,
    VIEW_PAYMENTS,
)
from foundation.database.session import get_db
from foundation.errors import AppError
from foundation.web.dependencies import FranchiseScope, UserContext, get_franchise_scope, require_permissions
from foundation.web.responses import error_response, internal_error_response, success_response

router = APIRouter(prefix="/payments", tags=["payments"])


@router.get("")
def list_payments(
        invoice_id: int | None = Query(default=None),
        mode: PaymentMode | None = Query(default=None),
        verified_by: int | None = Query(default=None),
        context: UserContext = Depends(require_permissions(VIEW_PAYMENTS)),
        db: Session = Depends(get_db),
) -> JSONResponse:
    """List payments (franchise-scoped via invoice); optional filters.

    **Query:** `invoice_id`, `mode` (`PaymentMode`), `verified_by` (user id).

    **Auth:** `VIEW_PAYMENTS`.

    **Success:** 200 — `data`: array of `{ id, invoice_id, amount, mode, verified_by, reference_number }`.
    **Errors:** `MISSING_FRANCHISE_CONTEXT`, etc. 422 / 500.
    """
    try:
        payments = list_payments_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            invoice_id=invoice_id,
            mode=mode,
            verified_by=verified_by,
        )
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    else:
        return success_response(
            message="Payments fetched successfully.",
            data=[serialize_payment_list_row(p) for p in payments],
            status_code=http_status.HTTP_200_OK,
        )


@router.post("", include_in_schema=False)
def create_payment(
        _context: UserContext = Depends(require_permissions(RECORD_PAYMENT)),
        _scope: FranchiseScope = Depends(get_franchise_scope),
) -> JSONResponse:
    return error_response(
        AppError(
            status_code=http_status.HTTP_501_NOT_IMPLEMENTED,
            message=
            "Creating payments via POST /payments is not available in API v1; use POST /invoices/{invoice_id}/payments.",
            error_code="NOT_AVAILABLE_IN_V1",
            details={"endpoint": "POST /payments"},
        ))


@router.patch("/{payment_id}")
def patch_payment(
        payment_id: int,
        payload: PatchPaymentReferenceRequest,
        context: UserContext = Depends(
            require_permissions(UPDATE_PAYMENT_REFERENCE)),
        db: Session = Depends(get_db),
) -> JSONResponse:
    """Update only `reference_number` on a payment (other fields immutable).

    **Path:** `payment_id`. **Body:** `PatchPaymentReferenceRequest` — `reference_number` (optional/null to clear).

    **Auth:** `UPDATE_PAYMENT_REFERENCE`.

    **Success:** 200 — `data`: `{ id, updated_at }`.
    **Errors:** `PAYMENT_NOT_FOUND`, `MISSING_FRANCHISE_CONTEXT`, … 422 / 500.
    """
    try:
        payment = patch_payment_reference_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            payment_id=payment_id,
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
            message="Payment updated successfully.",
            data=serialize_payment_patch_response(payment),
            status_code=http_status.HTTP_200_OK,
        )


@router.get("/{payment_id}")
def get_payment(
        payment_id: int,
        context: UserContext = Depends(require_permissions(VIEW_PAYMENTS)),
        db: Session = Depends(get_db),
) -> JSONResponse:
    """Payment detail with nested invoice snapshot and verifier user summary.

    **Path:** `payment_id`. **Auth:** `VIEW_PAYMENTS`.

    **Success:** 200 — `data`: `payment` (incl. timestamps), `invoice`, `verified_by_user`.
    **Errors:** `PAYMENT_NOT_FOUND`, `INVOICE_NOT_FOUND`, … 422 / 500.
    """
    try:
        payment, invoice, verifier = get_payment_detail_bundle_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            payment_id=payment_id,
        )
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    else:
        return success_response(
            message="Payment fetched successfully.",
            data=serialize_payment_detail(
                payment=payment,
                invoice=invoice,
                verifier=verifier,
            ),
            status_code=http_status.HTTP_200_OK,
        )
