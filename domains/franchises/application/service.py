from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from fastapi import status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from domains.audit.application.service import write_audit_log
from domains.bookings.infrastructure.models import Booking
from domains.customers.infrastructure.models import Customer
from domains.invoicing.infrastructure.models import Invoice
from domains.payments.infrastructure.models import Payment
from domains.franchises.domain.enums import DayOfWeek, FranchiseStatus
from domains.franchises.interfaces.schemas import (
    PatchFranchiseReviewRequest,
    PatchFranchiseTimingRequest,
)
from domains.franchises.infrastructure.models import (
    CommissionPolicy,
    Franchise,
    FranchiseReview,
    FranchiseTiming,
    new_franchise_code_placeholder,
)
from domains.users.domain.access import UserRole
from domains.users.infrastructure.models import User
from foundation.errors import AppError

logger = logging.getLogger(__name__)

_MONEY_QUANT = Decimal("0.01")


def _money_str(value: Decimal) -> str:
    return str(value.quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP))


def _franchise_extended_metrics(db: Session, franchise_id: int) -> dict:
    """Aggregates for list/detail franchise payloads (``api_contracts`` extended fields)."""
    avg_rating = db.scalar(
        select(func.avg(FranchiseReview.rating)).where(
            FranchiseReview.franchise_id == franchise_id, ), )
    average_rating: str | None
    if avg_rating is None:
        average_rating = None
    else:
        d = avg_rating if isinstance(avg_rating, Decimal) else Decimal(
            str(avg_rating))
        average_rating = str(d.quantize(Decimal("0.1"),
                                        rounding=ROUND_HALF_UP))

    last_dt = db.scalar(
        select(func.max(Invoice.created_at)).where(
            Invoice.franchise_id == franchise_id, ), )
    last_invoice_datetime = last_dt.isoformat(
    ) if last_dt is not None else None

    tic = db.scalar(
        select(func.count()).select_from(Invoice).where(
            Invoice.franchise_id == franchise_id, ), )
    total_invoices = int(tic or 0)

    svc = db.scalar(
        select(func.count(func.distinct(Booking.vehicle_id))).where(
            Booking.franchise_id == franchise_id, ), )
    total_served_vehicles = int(svc or 0)

    now = datetime.now(timezone.utc)
    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_today = start_today + timedelta(days=1)

    today_sum = db.scalar(
        select(func.coalesce(func.sum(Payment.amount),
                             0)).select_from(Payment).join(
                                 Invoice,
                                 Payment.invoice_id == Invoice.id).where(
                                     Invoice.franchise_id == franchise_id,
                                     Payment.created_at >= start_today,
                                     Payment.created_at < end_today,
                                 ), )
    today_revenue = _money_str(today_sum if isinstance(today_sum, Decimal) else
                               Decimal(str(today_sum or 0)))

    start_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if now.month == 12:
        end_month = start_month.replace(year=now.year + 1, month=1)
    else:
        end_month = start_month.replace(month=now.month + 1)

    month_sum = db.scalar(
        select(func.coalesce(func.sum(Payment.amount),
                             0)).select_from(Payment).join(
                                 Invoice,
                                 Payment.invoice_id == Invoice.id).where(
                                     Invoice.franchise_id == franchise_id,
                                     Payment.created_at >= start_month,
                                     Payment.created_at < end_month,
                                 ), )
    monthly_revenue = _money_str(month_sum if isinstance(month_sum, Decimal)
                                 else Decimal(str(month_sum or 0)))

    return {
        "average_rating": average_rating,
        "last_invoice_datetime": last_invoice_datetime,
        "today_revenue": today_revenue,
        "monthly_revenue": monthly_revenue,
        "total_invoices": total_invoices,
        "total_served_vehicles": total_served_vehicles,
    }


def serialize_franchise_row(
    db: Session,
    franchise: Franchise,
    *,
    include_extended: bool = True,
) -> dict:
    data: dict = {
        "id": franchise.id,
        "name": franchise.name,
        "code": franchise.code,
        "address": franchise.address,
        "city": franchise.city,
        "state": franchise.state,
        "pincode": franchise.pincode,
        "country": franchise.country,
        "location_url": franchise.location_url,
        "description": franchise.description,
        "created_at": str(franchise.created_at),
        "updated_at": str(franchise.updated_at),
    }
    if not include_extended:
        return data

    data["status"] = franchise.status.value
    data["gst_number"] = franchise.gst_number
    data["pan_number"] = franchise.pan_number
    data["monthly_target"] = str(
        franchise.monthly_target
    ) if franchise.monthly_target is not None else None

    # TODO : add these info when booking module is implemented
    data.update(_franchise_extended_metrics(db, franchise.id))
    return data


def create_franchise_for_actor(
    db: Session,
    *,
    actor: User,
    name: str,
    address: str,
    city: str,
    state: str,
    pincode: str,
    country: str,
    location_url: str | None,
    gst_number: str,
    pan_number: str,
    monthly_target: Decimal | None,
    description: str | None,
) -> Franchise:
    """Persist a franchise. Body fields are expected to match ``CreateFranchiseRequest`` (validated there)."""

    franchise = Franchise(
        name=name,
        code=new_franchise_code_placeholder(),
        address=address,
        city=city,
        state=state,
        pincode=pincode,
        country=country,
        status=FranchiseStatus.PENDING_APPROVAL,
        gst_number=gst_number,
        pan_number=pan_number,
        monthly_target=monthly_target,
        location_url=location_url,
        description=description,
    )
    db.add(franchise)
    db.flush()

    for day in DayOfWeek:
        timing = FranchiseTiming(
            franchise_id=franchise.id,
            day_of_week=day,
            open_time=None,
            close_time=None,
            is_closed=True,
        )
        db.add(timing)
    db.flush()

    write_audit_log(
        db,
        action="franchise.create",
        entity_name="franchises",
        entity_id=str(franchise.id),
        actor_user_id=actor.id,
        franchise_id=franchise.id,
        payload={
            "code": franchise.code,
            "name": name
        },
    )
    return franchise


def list_franchises_for_actor(
    db: Session,
    *,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    search: str | None,
    code: str | None,
    name: str | None,
    city: str | None,
    state: str | None,
    country: str | None,
    status: FranchiseStatus | None,
) -> list[Franchise]:
    statement = select(Franchise).order_by(Franchise.name.asc())
    if status is not None:
        statement = statement.where(Franchise.status == status)
    if code:
        statement = statement.where(Franchise.code.ilike(f"%{code}%"))
    if name:
        statement = statement.where(Franchise.name.ilike(f"%{name}%"))
    if city:
        statement = statement.where(Franchise.city.ilike(f"%{city}%"))
    if state:
        statement = statement.where(Franchise.state.ilike(f"%{state}%"))
    if country:
        statement = statement.where(Franchise.country.ilike(f"%{country}%"))
    if search:
        q = f"%{search}%"
        statement = statement.where(
            or_(
                Franchise.name.ilike(q),
                Franchise.code.ilike(q),
                Franchise.city.ilike(q),
                Franchise.state.ilike(q),
                Franchise.country.ilike(q),
            ))

    if actor_role is not UserRole.MAIN_ADMIN:
        if actor_franchise_id is None:
            raise AppError(
                status_code=status.HTTP_403_FORBIDDEN,
                message="Franchise context is required.",
                error_code="MISSING_FRANCHISE_CONTEXT",
            )
        statement = statement.where(Franchise.id == actor_franchise_id)

    return list(db.scalars(statement).all())


def get_franchise_for_actor(
    db: Session,
    *,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    franchise_id: int,
) -> Franchise:
    if actor_role in (
            UserRole.FRANCHISE_ADMIN,
            UserRole.FRANCHISE_STAFF_MEMBER,
    ):
        if actor_franchise_id is None:
            raise AppError(
                status_code=status.HTTP_403_FORBIDDEN,
                message="Franchise context is required.",
                error_code="MISSING_FRANCHISE_CONTEXT",
            )
        if actor_franchise_id != franchise_id:
            raise AppError(
                status_code=status.HTTP_403_FORBIDDEN,
                message="You cannot access this franchise information.",
                error_code="FORBIDDEN_FOREIGN_FRANCHISE",
                details={
                    "requested_franchise_id": franchise_id,
                    "actor_franchise_id": actor_franchise_id,
                },
            )

    franchise = db.scalar(
        select(Franchise).where(Franchise.id == franchise_id))
    if franchise is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Franchise not found.",
            error_code="FRANCHISE_NOT_FOUND",
            details={"franchise_id": franchise_id},
        )
    return franchise


def serialize_commission_policy_row(policy: CommissionPolicy) -> dict:
    """POST commission policy response (``api_contracts``)."""
    return {
        "id": policy.id,
        "franchise_id": policy.franchise_id,
        "percentage": str(policy.percentage),
        "effective_from": policy.effective_from.isoformat(),
        "is_active": policy.is_active,
    }


def serialize_commission_policy_list_item(policy: CommissionPolicy) -> dict:
    """One commission policy row for GET list (no embedded franchise)."""
    return {
        "id":
        policy.id,
        "franchise_id":
        policy.franchise_id,
        "percentage":
        str(policy.percentage),
        "effective_from":
        policy.effective_from.isoformat(),
        "effective_till":
        policy.effective_till.isoformat()
        if policy.effective_till is not None else None,
        "is_active":
        policy.is_active,
    }


def serialize_active_commission_policy_response(
    db: Session,
    *,
    policy: CommissionPolicy | None,
    franchise: Franchise,
    include_extended_franchise: bool,
) -> dict:
    """GET active commission policy payload: policy fields only when ``policy`` is set."""
    if policy is None:
        return {}
    return {
        "id":
        policy.id,
        "franchise_id":
        policy.franchise_id,
        "percentage":
        str(policy.percentage),
        "effective_from":
        policy.effective_from.isoformat(),
        "franchise_details":
        serialize_franchise_row(
            db,
            franchise,
            include_extended=include_extended_franchise,
        ),
    }


def list_commission_policies_for_actor(
    db: Session,
    *,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    franchise_id: int,
    active_only: bool = False,
) -> tuple[Franchise, list[CommissionPolicy]]:
    franchise = get_franchise_for_actor(
        db,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        franchise_id=franchise_id,
    )
    statement = select(CommissionPolicy).where(
        CommissionPolicy.franchise_id == franchise_id, )
    if active_only:
        statement = statement.where(CommissionPolicy.is_active.is_(True))
    statement = statement.order_by(
        CommissionPolicy.effective_from.desc(),
        CommissionPolicy.id.desc(),
    )
    policies = list(db.scalars(statement).all())
    return franchise, policies


def _sorted_franchise_timings(
        timings: list[FranchiseTiming]) -> list[FranchiseTiming]:
    order = {
        DayOfWeek.SUNDAY: 0,
        DayOfWeek.MONDAY: 1,
        DayOfWeek.TUESDAY: 2,
        DayOfWeek.WEDNESDAY: 3,
        DayOfWeek.THURSDAY: 4,
        DayOfWeek.FRIDAY: 5,
        DayOfWeek.SATURDAY: 6,
    }
    return sorted(timings, key=lambda t: order[t.day_of_week])


def serialize_franchise_timing_list_item(timing: FranchiseTiming) -> dict:
    """One timing row for GET list (no embedded franchise)."""
    return {
        "id":
        timing.id,
        "franchise_id":
        timing.franchise_id,
        "day_of_week":
        timing.day_of_week.value,
        "open_time":
        timing.open_time.isoformat() if timing.open_time is not None else None,
        "close_time":
        timing.close_time.isoformat()
        if timing.close_time is not None else None,
        "is_closed":
        timing.is_closed,
    }


def list_franchise_timings_for_actor(
    db: Session,
    *,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    franchise_id: int,
) -> tuple[Franchise, list[FranchiseTiming]]:
    """All timing slots for the franchise, Sunday-Saturday order."""
    franchise = get_franchise_for_actor(
        db,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        franchise_id=franchise_id,
    )
    rows = list(
        db.scalars(
            select(FranchiseTiming).where(
                FranchiseTiming.franchise_id == franchise_id, ), ).all(), )
    return franchise, _sorted_franchise_timings(rows)


def serialize_franchise_timing_patch_response(timing: FranchiseTiming) -> dict:
    """PATCH timing response (``api_contracts``)."""
    return {
        "id":
        timing.id,
        "franchise_id":
        timing.franchise_id,
        "day_of_week":
        timing.day_of_week.value,
        "open_time":
        timing.open_time.isoformat() if timing.open_time is not None else None,
        "close_time":
        timing.close_time.isoformat()
        if timing.close_time is not None else None,
        "is_closed":
        timing.is_closed,
        "updated_at":
        timing.updated_at.isoformat(),
    }


def patch_franchise_timing_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    franchise_id: int,
    day_of_week: DayOfWeek,
    payload: PatchFranchiseTimingRequest,
) -> FranchiseTiming:
    get_franchise_for_actor(
        db,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        franchise_id=franchise_id,
    )
    timing = db.scalar(
        select(FranchiseTiming).where(
            FranchiseTiming.franchise_id == franchise_id,
            FranchiseTiming.day_of_week == day_of_week,
        ), )
    if timing is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Franchise timing not found for this day.",
            error_code="FRANCHISE_TIMING_NOT_FOUND",
            details={
                "franchise_id": franchise_id,
                "day_of_week": day_of_week.value,
            },
        )
    timing.is_closed = payload.is_closed
    if payload.is_closed:
        timing.open_time = None
        timing.close_time = None
    else:
        timing.open_time = payload.open_time
        timing.close_time = payload.close_time

    db.flush()
    db.refresh(timing)

    write_audit_log(
        db,
        action="franchise_timing.update",
        entity_name="franchise_timings",
        entity_id=str(timing.id),
        actor_user_id=actor.id,
        franchise_id=franchise_id,
        payload={"day_of_week": day_of_week.value},
    )
    return timing


def create_commission_policy_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    franchise_id: int,
    commission_percentage: Decimal,
) -> CommissionPolicy:
    """Create a new active commission policy; deactivates any prior active policy for the franchise."""
    get_franchise_for_actor(
        db,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        franchise_id=franchise_id,
    )

    effective_from = date.today()
    # Invariant: at most one active policy per franchise; expect 0–1 rows.
    previous_active_commission_policies = list(
        db.scalars(
            select(CommissionPolicy).where(
                CommissionPolicy.franchise_id == franchise_id,
                CommissionPolicy.is_active.is_(True),
            ), ).all(), )

    end_previous_active_commission_policy = effective_from - timedelta(days=1)

    for previous_active_commission_policy in previous_active_commission_policies:
        previous_active_commission_policy.is_active = False
        if end_previous_active_commission_policy >= previous_active_commission_policy.effective_from:
            previous_active_commission_policy.effective_till = end_previous_active_commission_policy
        else:
            previous_active_commission_policy.effective_till = previous_active_commission_policy.effective_from

    policy = CommissionPolicy(
        franchise_id=franchise_id,
        percentage=commission_percentage,
        effective_from=effective_from,
        effective_till=None,
        is_active=True,
    )
    db.add(policy)
    db.flush()

    write_audit_log(
        db,
        action="franchise_commission_policy.create",
        entity_name="franchise_commission_policies",
        entity_id=str(policy.id),
        actor_user_id=actor.id,
        franchise_id=franchise_id,
        payload={
            "percentage": str(commission_percentage),
            "effective_from": effective_from.isoformat(),
        },
    )
    return policy


def update_franchise_for_actor(
    db: Session,
    *,
    actor: User,
    franchise_id: int,
    name: str | None,
    address: str | None,
    city: str | None,
    state: str | None,
    pincode: str | None,
    country: str | None,
    gst_number: str | None,
    pan_number: str | None,
    monthly_target: Decimal | None,
    location_url: str | None,
    description: str | None,
) -> Franchise:
    """Partial update. Provided fields are expected to match ``UpdateFranchiseRequest`` (validated there)."""

    franchise = db.scalar(
        select(Franchise).where(Franchise.id == franchise_id))
    if franchise is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Franchise not found.",
            error_code="FRANCHISE_NOT_FOUND",
            details={"franchise_id": franchise_id},
        )

    if name is not None:
        franchise.name = name
    if address is not None:
        franchise.address = address
    if city is not None:
        franchise.city = city
    if state is not None:
        franchise.state = state
    if pincode is not None:
        franchise.pincode = pincode
    if country is not None:
        franchise.country = country
    if gst_number is not None:
        franchise.gst_number = gst_number
    if pan_number is not None:
        franchise.pan_number = pan_number
    if monthly_target is not None:
        franchise.monthly_target = monthly_target
    if location_url is not None:
        franchise.location_url = location_url
    if description is not None:
        franchise.description = description

    db.add(franchise)
    db.flush()

    write_audit_log(
        db,
        action="franchise.update",
        entity_name="franchises",
        entity_id=str(franchise.id),
        actor_user_id=actor.id,
        franchise_id=franchise.id,
        payload={"fields": "partial"},
    )
    return franchise


def set_franchise_active_status_for_actor(
    db: Session,
    *,
    actor: User,
    franchise_id: int,
    active: bool,
) -> Franchise:
    franchise = db.scalar(
        select(Franchise).where(Franchise.id == franchise_id))
    if franchise is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Franchise not found.",
            error_code="FRANCHISE_NOT_FOUND",
            details={"franchise_id": franchise_id},
        )

    if active:
        if franchise.status is FranchiseStatus.ACTIVE:
            return franchise
        franchise.status = FranchiseStatus.ACTIVE
    else:
        if franchise.status not in {
                FranchiseStatus.ACTIVE,
                FranchiseStatus.PENDING_APPROVAL,
        }:
            raise AppError(
                status_code=status.HTTP_400_BAD_REQUEST,
                message=
                ("Can only deactivate a franchise that is active or pending approval."
                 ),
                error_code="FRANCHISE_INVALID_STATUS_FOR_DEACTIVATE",
                details={"status": franchise.status.value},
            )
        franchise.status = FranchiseStatus.INACTIVE

    db.add(franchise)
    db.flush()

    write_audit_log(
        db,
        action="franchise.activate" if active else "franchise.deactivate",
        entity_name="franchises",
        entity_id=str(franchise.id),
        actor_user_id=actor.id,
        franchise_id=franchise.id,
        payload={"status": franchise.status.value},
    )
    return franchise


def serialize_franchise_review_row(review: FranchiseReview) -> dict:
    return {
        "id": review.id,
        "franchise_id": review.franchise_id,
        "customer_id": review.customer_id,
        "rating": str(review.rating),
        "comment": review.comment,
        "created_at": review.created_at.isoformat(),
        "updated_at": review.updated_at.isoformat(),
    }


def serialize_franchise_review_detail_response(
    db: Session,
    *,
    review: FranchiseReview,
    franchise: Franchise,
    include_extended_franchise: bool,
) -> dict:
    """GET single review: review fields plus nested ``franchise_details``."""
    return {
        "id":
        review.id,
        "franchise_id":
        review.franchise_id,
        "customer_id":
        review.customer_id,
        "rating":
        str(review.rating),
        "comment":
        review.comment,
        "created_at":
        review.created_at.isoformat(),
        "updated_at":
        review.updated_at.isoformat(),
        "franchise_details":
        serialize_franchise_row(
            db,
            franchise,
            include_extended=include_extended_franchise,
        ),
    }


def list_franchise_reviews_for_actor(
    db: Session,
    *,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    franchise_id: int,
) -> tuple[Franchise, list[FranchiseReview]]:
    franchise = get_franchise_for_actor(
        db,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        franchise_id=franchise_id,
    )
    reviews = list(
        db.scalars(
            select(FranchiseReview).where(
                FranchiseReview.franchise_id == franchise_id, ).order_by(
                    FranchiseReview.created_at.desc()), ).all(), )
    return franchise, reviews


def get_franchise_review_for_actor(
    db: Session,
    *,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    franchise_id: int,
    review_id: int,
) -> tuple[Franchise, FranchiseReview]:
    franchise = get_franchise_for_actor(
        db,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        franchise_id=franchise_id,
    )
    review = db.scalar(
        select(FranchiseReview).where(
            FranchiseReview.id == review_id,
            FranchiseReview.franchise_id == franchise_id,
        ), )
    if review is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Review not found.",
            error_code="FRANCHISE_REVIEW_NOT_FOUND",
            details={
                "franchise_id": franchise_id,
                "review_id": review_id,
            },
        )
    return franchise, review


def create_franchise_review_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    franchise_id: int,
    customer_id: int,
    rating: Decimal,
    comment: str | None,
) -> FranchiseReview:
    """``comment`` is expected to match ``CreateFranchiseReviewRequest`` (validated there)."""

    get_franchise_for_actor(
        db,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        franchise_id=franchise_id,
    )
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Customer not found.",
            error_code="CUSTOMER_NOT_FOUND",
            details={"customer_id": customer_id},
        )
    if customer.franchise_id != franchise_id:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Customer does not belong to this franchise.",
            error_code="CUSTOMER_NOT_IN_FRANCHISE",
            details={
                "customer_id": customer_id,
                "franchise_id": franchise_id,
            },
        )

    review = FranchiseReview(
        franchise_id=franchise_id,
        customer_id=customer_id,
        rating=rating,
        comment=comment,
    )
    db.add(review)
    db.flush()

    write_audit_log(
        db,
        action="franchise_review.create",
        entity_name="franchise_reviews",
        entity_id=str(review.id),
        actor_user_id=actor.id,
        franchise_id=franchise_id,
        payload={"customer_id": customer_id},
    )
    return review


def serialize_franchise_review_patch_response(review: FranchiseReview) -> dict:
    return {
        "id": review.id,
        "updated_at": review.updated_at.isoformat(),
    }


def patch_franchise_review_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    franchise_id: int,
    review_id: int,
    payload: PatchFranchiseReviewRequest,
) -> FranchiseReview:
    get_franchise_for_actor(
        db,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        franchise_id=franchise_id,
    )
    if not payload.model_fields_set:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="No fields to update.",
            error_code="NO_FIELDS_TO_UPDATE",
            details={},
        )

    review = db.scalar(
        select(FranchiseReview).where(
            FranchiseReview.id == review_id,
            FranchiseReview.franchise_id == franchise_id,
        ), )
    if review is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Review not found.",
            error_code="FRANCHISE_REVIEW_NOT_FOUND",
            details={
                "franchise_id": franchise_id,
                "review_id": review_id,
            },
        )

    if "rating" in payload.model_fields_set:
        if payload.rating is None:
            raise AppError(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="Rating cannot be cleared.",
                error_code="FRANCHISE_REVIEW_RATING_REQUIRED",
                details={},
            )
        review.rating = payload.rating
    if "comment" in payload.model_fields_set:
        review.comment = payload.comment

    db.flush()
    db.refresh(review)

    write_audit_log(
        db,
        action="franchise_review.update",
        entity_name="franchise_reviews",
        entity_id=str(review.id),
        actor_user_id=actor.id,
        franchise_id=franchise_id,
        payload={"review_id": review_id},
    )
    return review


def delete_franchise_not_supported() -> None:
    raise AppError(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        message="Deleting a franchise is not supported.",
        error_code="FRANCHISE_DELETE_NOT_SUPPORTED",
    )
