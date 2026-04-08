from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from starlette import status as http_status

from domains.franchises.application.service import list_franchises_by_performance_for_actor
from domains.users.domain.access import VIEW_FRANCHISES_BY_PERFORMANCE, VIEW_REPORTS
from domains.reports.application.service import (
    get_daily_dashboard,
    get_monthly_summary,
    list_pending_payment_rows,
)
from foundation.database.session import get_db
from foundation.errors import AppError
from foundation.web.dependencies import (
    FranchiseScope,
    UserContext,
    get_franchise_scope,
    require_permissions,
)
from foundation.web.responses import error_response, internal_error_response, success_response

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/franchises/by-performance", include_in_schema=False)
def list_franchises_by_performance(
        context: UserContext = Depends(
            require_permissions(VIEW_FRANCHISES_BY_PERFORMANCE)),
        db: Session = Depends(get_db),
) -> dict:
    """Franchise performance ranking (admin). **Auth:** `VIEW_FRANCHISES_BY_PERFORMANCE`. **Success:** 200 envelope. **Errors:** AppError; 422 / 500. Hidden from OpenAPI."""
    try:
        rows = list_franchises_by_performance_for_actor(db)
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    else:
        return success_response(
            message="Franchise performance ranking fetched successfully.",
            data=rows,
            status_code=http_status.HTTP_200_OK,
        )


@router.get("/daily")
def get_daily_report(
        business_date: date = Query(default_factory=date.today),
        db: Session = Depends(get_db),
        scope: FranchiseScope = Depends(get_franchise_scope),
        _: object = Depends(require_permissions(VIEW_REPORTS)),
) -> dict:
    """Daily metrics for scoped franchise (includes `payment_breakdown`). **Query:** `business_date` (default today). **Auth:** `VIEW_REPORTS` + franchise scope. **Success:** 200 plain dict (not standard envelope). **Errors:** 401/403 as deps."""
    dashboard = get_daily_dashboard(db,
                                    franchise_id=scope.franchise_id,
                                    business_date=business_date)
    return {
        "business_date": dashboard["business_date"].isoformat(),
        "registered_services": dashboard["registered_services"],
        "registered_revenue": str(dashboard["registered_revenue"]),
        "services_with_payment": dashboard["services_with_payment"],
        "payment_pending_services": dashboard["payment_pending_services"],
        "total_income": str(dashboard["total_income"]),
        "pending_income": str(dashboard["pending_income"]),
        "payment_breakdown": {
            "cash": str(dashboard["cash_income"]),
            "upi": str(dashboard["upi_income"]),
            "card": str(dashboard["card_income"]),
            "bank": str(dashboard["bank_income"]),
        },
    }


@router.get("/dashboard/daily")
def get_daily_dashboard_view(
        business_date: date = Query(default_factory=date.today),
        db: Session = Depends(get_db),
        scope: FranchiseScope = Depends(get_franchise_scope),
        _: object = Depends(require_permissions(VIEW_REPORTS)),
) -> dict:
    """Daily dashboard (extended fields vs `/reports/daily`). **Query:** `business_date`. **Auth:** `VIEW_REPORTS` + scope. **Success:** 200 plain dict."""
    dashboard = get_daily_dashboard(db,
                                    franchise_id=scope.franchise_id,
                                    business_date=business_date)
    return {
        "business_date": dashboard["business_date"].isoformat(),
        "registered_services": dashboard["registered_services"],
        "registered_revenue": str(dashboard["registered_revenue"]),
        "services_with_payment": dashboard["services_with_payment"],
        "payment_pending_services": dashboard["payment_pending_services"],
        "total_income": str(dashboard["total_income"]),
        "pending_income": str(dashboard["pending_income"]),
        "invoice_pending_amount": str(dashboard["invoice_pending_amount"]),
        "cash_income": str(dashboard["cash_income"]),
        "upi_income": str(dashboard["upi_income"]),
        "card_income": str(dashboard["card_income"]),
        "bank_income": str(dashboard["bank_income"]),
    }


@router.get("/monthly")
def get_monthly_report(
        year: int = Query(ge=2000, le=2100),
        month: int = Query(ge=1, le=12),
        db: Session = Depends(get_db),
        scope: FranchiseScope = Depends(get_franchise_scope),
        _: object = Depends(require_permissions(VIEW_REPORTS)),
) -> dict:
    """Monthly revenue summary. **Query:** `year`, `month`. **Auth:** `VIEW_REPORTS` + scope. **Success:** 200 plain dict."""
    summary = get_monthly_summary(db,
                                  franchise_id=scope.franchise_id,
                                  year=year,
                                  month=month)
    return {
        "year": summary["year"],
        "month": summary["month"],
        "booking_count": summary["booking_count"],
        "booked_revenue": str(summary["booked_revenue"]),
        "total_income": str(summary["total_income"]),
        "pending_income": str(summary["pending_income"]),
        "cash_income": str(summary["cash_income"]),
        "upi_income": str(summary["upi_income"]),
        "card_income": str(summary["card_income"]),
        "bank_income": str(summary["bank_income"]),
    }


@router.get("/pending-payments")
def get_pending_payments_report(
        db: Session = Depends(get_db),
        scope: FranchiseScope = Depends(get_franchise_scope),
        _: object = Depends(require_permissions(VIEW_REPORTS)),
) -> list[dict]:
    """Bookings/invoices with pending payment amounts. **Auth:** `VIEW_REPORTS` + scope. **Success:** 200 JSON array (plain, not envelope)."""
    rows = list_pending_payment_rows(db, franchise_id=scope.franchise_id)
    return [{
        "booking_id": row["booking_id"],
        "customer_id": row["customer_id"],
        "vehicle_id": row["vehicle_id"],
        "invoice_id": row["invoice_id"],
        "total_payable_amount": str(row["total_payable_amount"]),
        "total_paid_amount": str(row["total_paid_amount"]),
        "pending_amount": str(row["pending_amount"]),
    } for row in rows]
