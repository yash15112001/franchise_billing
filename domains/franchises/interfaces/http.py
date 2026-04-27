from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from starlette import status as http_status

from domains.franchises.application.service import (
    create_commission_policy_for_actor,
    create_franchise_for_actor,
    create_franchise_review_for_actor,
    get_franchise_for_actor,
    get_franchise_review_for_actor,
    list_commission_policies_for_actor,
    list_franchise_reviews_for_actor,
    list_franchise_timings_for_actor,
    list_franchises_for_actor,
    patch_franchise_review_for_actor,
    patch_franchise_timing_for_actor,
    serialize_active_commission_policy_response,
    serialize_commission_policy_list_item,
    serialize_commission_policy_row,
    soft_delete_franchise_for_actor,
    serialize_franchise_timing_list_item,
    serialize_franchise_review_detail_response,
    serialize_franchise_review_patch_response,
    serialize_franchise_review_row,
    serialize_franchise_timing_patch_response,
    serialize_franchise_row,
    set_franchise_active_status_for_actor,
    update_franchise_for_actor,
)
from domains.franchises.domain.enums import DayOfWeek, FranchiseStatus
from domains.franchises.interfaces.schemas import (
    CreateCommissionPolicyRequest,
    CreateFranchiseRequest,
    CreateFranchiseReviewRequest,
    PatchFranchiseReviewRequest,
    PatchFranchiseTimingRequest,
    UpdateFranchiseRequest,
)
from domains.users.domain.access import (
    ACTIVATE_FRANCHISES, CREATE_FRANCHISES,
    CREATE_FRANCHISE_COMMISSION_POLICIES, CREATE_FRANCHISE_REVIEWS,
    DEACTIVATE_FRANCHISES, DELETE_FRANCHISES, UPDATE_FRANCHISES, UPDATE_FRANCHISE_REVIEWS,
    UPDATE_FRANCHISE_TIMINGS, VIEW_FRANCHISES,
    VIEW_FRANCHISE_COMMISSION_POLICIES, VIEW_FRANCHISE_REVIEWS,
    VIEW_FRANCHISE_TIMINGS, UserRole)
from foundation.database.session import get_db
from foundation.errors import AppError
from foundation.web.dependencies import UserContext, require_permissions
from foundation.web.responses import error_response, internal_error_response, success_response
from sqlalchemy.orm import Session

router = APIRouter(prefix="/franchises", tags=["franchises"])

# --- Core franchise (register static paths before /{franchise_id}) ---


@router.get("")
def list_franchises(
        search: str | None = Query(default=None),
        code: str | None = Query(default=None),
        name: str | None = Query(default=None),
        city: str | None = Query(default=None),
        state: str | None = Query(default=None),
        country: str | None = Query(default=None),
        status: FranchiseStatus | None = Query(default=None),
        context: UserContext = Depends(require_permissions(VIEW_FRANCHISES)),
        db: Session = Depends(get_db),
) -> dict:
    """List franchises (role-scoped). **Query:** search, code, name, city, state, country, status. **Auth:** `VIEW_FRANCHISES`. **Success:** 200. **Errors:** AppError; 422 / 500.
    """
    try:
        franchises = list_franchises_for_actor(
            db,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            search=search,
            code=code,
            name=name,
            city=city,
            state=state,
            country=country,
            status=status,
        )
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    else:
        return success_response(
            message="Franchises fetched successfully.",
            data=[
                serialize_franchise_row(db,
                                        franchise,
                                        include_extended=context.role
                                        != UserRole.FRANCHISE_STAFF_MEMBER)
                for franchise in franchises
            ],
            status_code=http_status.HTTP_200_OK,
        )


@router.get("/{franchise_id}")
def get_franchise(
        franchise_id: int,
        context: UserContext = Depends(require_permissions(VIEW_FRANCHISES)),
        db: Session = Depends(get_db),
) -> dict:
    """Single franchise. **Path:** `franchise_id`. **Auth:** `VIEW_FRANCHISES`. **Success:** 200. **Errors:** AppError (e.g. not found); 422 / 500.
    """
    try:
        franchise = get_franchise_for_actor(
            db,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            franchise_id=franchise_id,
        )
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    else:
        return success_response(
            message="Franchise fetched successfully.",
            data=serialize_franchise_row(db,
                                         franchise,
                                         include_extended=context.role
                                         != UserRole.FRANCHISE_STAFF_MEMBER),
            status_code=http_status.HTTP_200_OK,
        )


@router.post("")
def create_franchise(
        payload: CreateFranchiseRequest,
        context: UserContext = Depends(require_permissions(CREATE_FRANCHISES)),
        db: Session = Depends(get_db),
) -> dict:
    """Create franchise. **Body:** `CreateFranchiseRequest`. **Auth:** `CREATE_FRANCHISES`. **Success:** 201. **Errors:** AppError; 422 / 500.
    """
    try:
        franchise = create_franchise_for_actor(
            db,
            actor=context.user,
            name=payload.name,
            address=payload.address,
            city=payload.city,
            state=payload.state,
            pincode=payload.pincode,
            country=payload.country,
            location_url=payload.location_url,
            gst_number=payload.gst_number,
            pan_number=payload.pan_number,
            monthly_target=payload.monthly_target,
            description=payload.description,
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
            message="Franchise created successfully.",
            data=serialize_franchise_row(db, franchise,
                                         include_extended=False),
            status_code=http_status.HTTP_201_CREATED,
        )


# TODO : think of permission scenarios
@router.patch("/{franchise_id}")
def update_franchise(
        franchise_id: int,
        payload: UpdateFranchiseRequest,
        context: UserContext = Depends(require_permissions(UPDATE_FRANCHISES)),
        db: Session = Depends(get_db),
) -> dict:
    """Partial update (fields optional in body). **Body:** `UpdateFranchiseRequest`. **Auth:** `UPDATE_FRANCHISES`. **Success:** 200. **Errors:** AppError; 422 / 500.
    """
    try:
        franchise = update_franchise_for_actor(
            db,
            actor=context.user,
            franchise_id=franchise_id,
            name=payload.name,
            address=payload.address,
            city=payload.city,
            state=payload.state,
            pincode=payload.pincode,
            country=payload.country,
            gst_number=payload.gst_number,
            pan_number=payload.pan_number,
            monthly_target=payload.monthly_target,
            location_url=payload.location_url,
            description=payload.description,
        )
        db.commit()
    except AppError as exc:
        db.rollback()
        return error_response(exc)
    except Exception:
        db.rollback()
        return internal_error_response()
    else:
        # TODO : proper response not returned
        return success_response(
            message="Franchise updated successfully.",
            data=serialize_franchise_row(db, franchise,
                                         include_extended=False),
            status_code=http_status.HTTP_200_OK,
        )


# TODO : decide weather activating/deactivating the franchise should affect its users' is_active status
@router.patch("/{franchise_id}/activate")
def activate_franchise(
        franchise_id: int,
        context: UserContext = Depends(
            require_permissions(ACTIVATE_FRANCHISES)),
        db: Session = Depends(get_db),
) -> dict:
    """Set franchise active. **Path:** `franchise_id`. **Auth:** `ACTIVATE_FRANCHISES`. **Success:** 200. **Errors:** AppError; 422 / 500.
    """
    try:
        franchise = set_franchise_active_status_for_actor(
            db,
            actor=context.user,
            franchise_id=franchise_id,
            active=True,
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
            message="Franchise activated successfully.",
            data=serialize_franchise_row(db, franchise,
                                         include_extended=False),
            status_code=http_status.HTTP_200_OK,
        )


@router.patch("/{franchise_id}/deactivate")
def deactivate_franchise(
        franchise_id: int,
        context: UserContext = Depends(
            require_permissions(DEACTIVATE_FRANCHISES)),
        db: Session = Depends(get_db),
) -> dict:
    """Set franchise inactive. **Path:** `franchise_id`. **Auth:** `DEACTIVATE_FRANCHISES`. **Success:** 200. **Errors:** AppError; 422 / 500.
    """
    try:
        franchise = set_franchise_active_status_for_actor(
            db,
            actor=context.user,
            franchise_id=franchise_id,
            active=False,
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
            message="Franchise deactivated successfully.",
            data=serialize_franchise_row(db, franchise,
                                         include_extended=False),
            status_code=http_status.HTTP_200_OK,
        )


@router.delete("/{franchise_id}")
def delete_franchise(
        franchise_id: int,
        context: UserContext = Depends(require_permissions(DELETE_FRANCHISES)),
        db: Session = Depends(get_db),
) -> dict:
    """Soft-delete a franchise and all dependent resources."""
    try:
        franchise = soft_delete_franchise_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            franchise_id=franchise_id,
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
            message="Franchise deleted successfully.",
            data={
                "id": franchise.id,
                "is_deleted": franchise.is_deleted,
                "updated_at": str(franchise.updated_at),
            },
            status_code=http_status.HTTP_200_OK,
        )


# --- Commission policies ---


@router.get("/{franchise_id}/commission-policies/active")
def get_active_commission_policy(
        franchise_id: int,
        context: UserContext = Depends(
            require_permissions(VIEW_FRANCHISE_COMMISSION_POLICIES)),
        db: Session = Depends(get_db),
) -> dict:
    """Active commission policy for franchise (or empty message if none). **Path:** `franchise_id`. **Auth:** `VIEW_FRANCHISE_COMMISSION_POLICIES`. **Success:** 200. **Errors:** AppError; 422 / 500.
    """
    try:
        franchise, policies = list_commission_policies_for_actor(
            db,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            franchise_id=franchise_id,
            active_only=True,
        )
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    else:
        policy = policies[0] if policies else None
        return success_response(
            message=("Active commission policy fetched successfully."
                     if policy is not None else
                     "No active commission policy for this franchise."),
            data=serialize_active_commission_policy_response(
                db,
                policy=policy,
                franchise=franchise,
                include_extended_franchise=context.role
                != UserRole.FRANCHISE_STAFF_MEMBER,
            ),
            status_code=http_status.HTTP_200_OK,
        )


@router.get("/{franchise_id}/commission-policies")
def list_commission_policies(
        franchise_id: int,
        context: UserContext = Depends(
            require_permissions(VIEW_FRANCHISE_COMMISSION_POLICIES)),
        db: Session = Depends(get_db),
) -> dict:
    """All commission policies + franchise summary. **Path:** `franchise_id`. **Auth:** `VIEW_FRANCHISE_COMMISSION_POLICIES`. **Success:** 200. **Errors:** AppError; 422 / 500.
    """
    try:
        franchise, policies = list_commission_policies_for_actor(
            db,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            franchise_id=franchise_id,
        )
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    else:
        return success_response(
            message="Commission policies fetched successfully.",
            data={
                "franchise_commission_policies":
                [serialize_commission_policy_list_item(p) for p in policies],
                "franchise_details":
                serialize_franchise_row(
                    db,
                    franchise,
                    include_extended=False,
                ),
            },
            status_code=http_status.HTTP_200_OK,
        )


@router.post("/{franchise_id}/commission-policies")
def create_commission_policy(
        franchise_id: int,
        payload: CreateCommissionPolicyRequest,
        context: UserContext = Depends(
            require_permissions(CREATE_FRANCHISE_COMMISSION_POLICIES)),
        db: Session = Depends(get_db),
) -> dict:
    """Create commission policy. **Body:** `CreateCommissionPolicyRequest`. **Path:** `franchise_id`. **Auth:** `CREATE_FRANCHISE_COMMISSION_POLICIES`. **Success:** 201. **Errors:** AppError; 422 / 500.
    """
    try:
        policy = create_commission_policy_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            franchise_id=franchise_id,
            commission_percentage=payload.commission_percentage,
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
            message="Commission policy created successfully.",
            data=serialize_commission_policy_row(policy),
            status_code=http_status.HTTP_201_CREATED,
        )


# --- Timings ---


@router.get("/{franchise_id}/timings")
def list_franchise_timings(
        franchise_id: int,
        context: UserContext = Depends(
            require_permissions(VIEW_FRANCHISE_TIMINGS)),
        db: Session = Depends(get_db),
) -> dict:
    """Weekly timings + franchise details. **Path:** `franchise_id`. **Auth:** `VIEW_FRANCHISE_TIMINGS`. **Success:** 200. **Errors:** AppError; 422 / 500.
    """
    try:
        franchise, timings = list_franchise_timings_for_actor(
            db,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            franchise_id=franchise_id,
        )
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    else:
        include_extended = context.role != UserRole.FRANCHISE_STAFF_MEMBER
        return success_response(
            message="Franchise timings fetched successfully.",
            data={
                "franchise_timings":
                [serialize_franchise_timing_list_item(t) for t in timings],
                "franchise_details":
                serialize_franchise_row(
                    db,
                    franchise,
                    include_extended=include_extended,
                ),
            },
            status_code=http_status.HTTP_200_OK,
        )


@router.patch("/{franchise_id}/timings/{day_of_week}")
def patch_franchise_timing(
        franchise_id: int,
        day_of_week: DayOfWeek,
        payload: PatchFranchiseTimingRequest,
        context: UserContext = Depends(
            require_permissions(UPDATE_FRANCHISE_TIMINGS)),
        db: Session = Depends(get_db),
) -> dict:
    """Update one day’s timing. **Path:** `franchise_id`, `day_of_week` (enum). **Body:** `PatchFranchiseTimingRequest`. **Auth:** `UPDATE_FRANCHISE_TIMINGS`. **Success:** 200. **Errors:** AppError; 422 / 500.
    """
    try:
        timing = patch_franchise_timing_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            franchise_id=franchise_id,
            day_of_week=day_of_week,
            payload=payload,
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
            message="Franchise timing updated successfully.",
            data=serialize_franchise_timing_patch_response(timing),
            status_code=http_status.HTTP_200_OK,
        )


# --- Reviews ---


@router.get("/{franchise_id}/reviews")
def list_franchise_reviews(
        franchise_id: int,
        context: UserContext = Depends(
            require_permissions(VIEW_FRANCHISE_REVIEWS)),
        db: Session = Depends(get_db),
) -> dict:
    """List reviews + franchise summary. **Path:** `franchise_id`. **Auth:** `VIEW_FRANCHISE_REVIEWS`. **Success:** 200. **Errors:** AppError; 422 / 500.
    """
    try:
        franchise, reviews = list_franchise_reviews_for_actor(
            db,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            franchise_id=franchise_id,
        )
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    else:
        return success_response(
            message="Franchise reviews fetched successfully.",
            data={
                "reviews":
                [serialize_franchise_review_row(r) for r in reviews],
                "franchise_details":
                serialize_franchise_row(
                    db,
                    franchise,
                    include_extended=False,
                ),
            },
            status_code=http_status.HTTP_200_OK,
        )


@router.get("/{franchise_id}/reviews/{review_id}")
def get_franchise_review(
        franchise_id: int,
        review_id: int,
        context: UserContext = Depends(
            require_permissions(VIEW_FRANCHISE_REVIEWS)),
        db: Session = Depends(get_db),
) -> dict:
    """Single review with franchise context. **Path:** `franchise_id`, `review_id`. **Auth:** `VIEW_FRANCHISE_REVIEWS`. **Success:** 200. **Errors:** AppError; 422 / 500.
    """
    try:
        franchise, review = get_franchise_review_for_actor(
            db,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            franchise_id=franchise_id,
            review_id=review_id,
        )
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    else:
        include_extended = context.role != UserRole.FRANCHISE_STAFF_MEMBER
        return success_response(
            message="Franchise review fetched successfully.",
            data=serialize_franchise_review_detail_response(
                db,
                review=review,
                franchise=franchise,
                include_extended_franchise=include_extended,
            ),
            status_code=http_status.HTTP_200_OK,
        )


@router.post("/{franchise_id}/reviews")
def create_franchise_review(
        franchise_id: int,
        payload: CreateFranchiseReviewRequest,
        context: UserContext = Depends(
            require_permissions(CREATE_FRANCHISE_REVIEWS)),
        db: Session = Depends(get_db),
) -> dict:
    """Create review. **Body:** `CreateFranchiseReviewRequest`. **Path:** `franchise_id`. **Auth:** `CREATE_FRANCHISE_REVIEWS`. **Success:** 201. **Errors:** AppError; 422 / 500.
    """
    try:
        review = create_franchise_review_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            franchise_id=franchise_id,
            customer_id=payload.customer_id,
            rating=payload.rating,
            comment=payload.comment,
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
            message="Franchise review created successfully.",
            data=serialize_franchise_review_row(review),
            status_code=http_status.HTTP_201_CREATED,
        )


@router.patch("/{franchise_id}/reviews/{review_id}")
def patch_franchise_review(
        franchise_id: int,
        review_id: int,
        payload: PatchFranchiseReviewRequest,
        context: UserContext = Depends(
            require_permissions(UPDATE_FRANCHISE_REVIEWS)),
        db: Session = Depends(get_db),
) -> dict:
    """Partial update review. **Body:** `PatchFranchiseReviewRequest`. **Path:** `franchise_id`, `review_id`. **Auth:** `UPDATE_FRANCHISE_REVIEWS`. **Success:** 200. **Errors:** AppError; 422 / 500.
    """
    try:
        review = patch_franchise_review_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            franchise_id=franchise_id,
            review_id=review_id,
            payload=payload,
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
            message="Franchise review updated successfully.",
            data=serialize_franchise_review_patch_response(review),
            status_code=http_status.HTTP_200_OK,
        )
