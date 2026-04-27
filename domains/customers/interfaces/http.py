from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from starlette import status

from domains.customers.application.service import (
    create_customer_for_actor,
    create_vehicle_for_actor,
    get_customer_history_for_actor,
    get_customer_list_row_for_actor,
    get_vehicle_for_actor,
    list_customers_for_actor,
    list_vehicles_for_actor,
    soft_delete_customer_for_actor,
    soft_delete_vehicle_for_actor,
    update_customer_for_actor,
    update_vehicle_for_actor,
)
from domains.customers.infrastructure.models import CustomerType
from domains.customers.interfaces.serializers import (
    serialize_customer_core,
    serialize_customer_list_row,
    serialize_customer_patch_response,
    serialize_vehicle_detail_response,
    serialize_vehicle_list_response,
    serialize_vehicle_patch_response,
    serialize_vehicle_row,
)
from domains.customers.interfaces.schemas import (
    CustomerCreateRequest,
    CustomerPatchRequest,
    VehicleCreateRequest,
    VehiclePatchRequest,
)
from domains.users.domain.access import (
    CREATE_CUSTOMERS,
    CREATE_VEHICLES,
    DELETE_CUSTOMERS,
    DELETE_VEHICLES,
    UPDATE_CUSTOMERS,
    UPDATE_VEHICLES,
    VIEW_CUSTOMER_HISTORY,
    VIEW_CUSTOMERS,
    VIEW_VEHICLES,
)
from foundation.database.session import get_db
from foundation.errors import AppError
from foundation.web.dependencies import UserContext, require_permissions
from foundation.web.responses import error_response, internal_error_response, success_response

customers_router = APIRouter(prefix="/customers", tags=["customers"])
vehicles_router = APIRouter(prefix="/vehicles", tags=["vehicles"])

# --- Customer  ---


@customers_router.get("")
def list_customers(
        search: str | None = Query(default=None),
        franchise_id: int | None = Query(default=None),
        full_name: str | None = Query(default=None),
        customer_type: CustomerType | None = Query(default=None),
        mobile_number: str | None = Query(default=None),
        whatsapp_number: str | None = Query(default=None),
        email: str | None = Query(default=None),
        context: UserContext = Depends(require_permissions(VIEW_CUSTOMERS)),
        db: Session = Depends(get_db),
) -> dict:
    """List customers (franchise-scoped). **Query:** filters as listed. **Auth:** `VIEW_CUSTOMERS`. **Success:** 200. **Errors:** AppError; 422 / 500.
    """
    try:
        customers_aggregate_info = list_customers_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            franchise_id=franchise_id,
            search=search,
            full_name=full_name,
            customer_type=customer_type,
            mobile_number=mobile_number,
            whatsapp_number=whatsapp_number,
            email=email,
        )
    except AppError as exc:
        return error_response(exc)
    except Exception as e:
        print(e)
        return internal_error_response()
    else:
        return success_response(
            message="Customers fetched successfully.",
            data=[
                serialize_customer_list_row(r)
                for r in customers_aggregate_info
            ],
            status_code=status.HTTP_200_OK,
        )


# testing : pending
@customers_router.get("/{customer_id}/history")
def get_customer_history(
        customer_id: int,
        context: UserContext = Depends(
            require_permissions(VIEW_CUSTOMER_HISTORY)),
        db: Session = Depends(get_db),
) -> dict:
    """Booking/history aggregate for a customer. **Path:** `customer_id`. **Auth:** `VIEW_CUSTOMER_HISTORY`. **Success:** 200. **Errors:** AppError. 422 / 500.
    """
    try:
        data = get_customer_history_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            customer_id=customer_id,
        )
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    else:
        return success_response(
            message="Customer history fetched successfully.",
            data=data,
            status_code=status.HTTP_200_OK,
        )


@customers_router.get("/{customer_id}")
def get_customer(
        customer_id: int,
        context: UserContext = Depends(require_permissions(VIEW_CUSTOMERS)),
        db: Session = Depends(get_db),
) -> dict:
    """Single customer list row. **Path:** `customer_id`. **Auth:** `VIEW_CUSTOMERS`. **Success:** 200. **Errors:** AppError. 422 / 500.
    """
    try:
        customer_aggregate_info = get_customer_list_row_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            customer_id=customer_id,
        )
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    else:
        return success_response(
            message="Customer fetched successfully.",
            data=serialize_customer_list_row(customer_aggregate_info),
            status_code=status.HTTP_200_OK,
        )


@customers_router.post("")
def create_customer(
        payload: CustomerCreateRequest,
        context: UserContext = Depends(require_permissions(CREATE_CUSTOMERS)),
        db: Session = Depends(get_db),
) -> dict:
    """Create customer. **Body:** `CustomerCreateRequest`. **Auth:** `CREATE_CUSTOMERS`. **Success:** 201. **Errors:** AppError. 422 / 500.
    """
    try:
        customer = create_customer_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            franchise_id=payload.franchise_id,
            full_name=payload.full_name,
            mobile_number=payload.mobile_number,
            whatsapp_number=payload.whatsapp_number,
            email=payload.email,
            customer_type=payload.customer_type,
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
            message="Customer created successfully.",
            data=serialize_customer_core(customer),
            status_code=status.HTTP_201_CREATED,
        )


@customers_router.patch("/{customer_id}")
def patch_customer(
        customer_id: int,
        payload: CustomerPatchRequest,
        context: UserContext = Depends(require_permissions(UPDATE_CUSTOMERS)),
        db: Session = Depends(get_db),
) -> dict:
    """Partial update. **Body:** `CustomerPatchRequest`. **Auth:** `UPDATE_CUSTOMERS`. **Success:** 200. **Errors:** AppError. 422 / 500.
    """
    try:
        customer = update_customer_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            customer_id=customer_id,
            full_name=payload.full_name,
            email=payload.email,
            mobile_number=payload.mobile_number,
            whatsapp_number=payload.whatsapp_number,
            customer_type=payload.customer_type,
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
            message="Customer updated successfully.",
            data=serialize_customer_patch_response(customer),
            status_code=status.HTTP_200_OK,
        )


@customers_router.delete("/{customer_id}")
def delete_customer(
        customer_id: int,
        context: UserContext = Depends(require_permissions(DELETE_CUSTOMERS)),
        db: Session = Depends(get_db),
) -> dict:
    """Soft-delete a customer, its vehicles, related booking tree, and reviews."""
    try:
        customer = soft_delete_customer_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            customer_id=customer_id,
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
            message="Customer deleted successfully.",
            data={
                "id": customer.id,
                "is_deleted": customer.is_deleted,
                "updated_at": str(customer.updated_at),
            },
            status_code=status.HTTP_200_OK,
        )


# --- Vehicles ---


@vehicles_router.get("")
def list_vehicles(
        search: str | None = Query(default=None),
        name: str | None = Query(default=None),
        customer_id: int | None = Query(default=None),
        franchise_id: int | None = Query(default=None),
        registration_number: str | None = Query(default=None),
        vehicle_type: str | None = Query(default=None),
        color: str | None = Query(default=None),
        model: str | None = Query(default=None),
        context: UserContext = Depends(require_permissions(VIEW_VEHICLES)),
        db: Session = Depends(get_db),
) -> dict:
    """List vehicles with filters. **Auth:** `VIEW_VEHICLES`. **Success:** 200. **Errors:** AppError. 422 / 500.
    """
    try:
        vehicles = list_vehicles_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            search=search,
            name=name,
            customer_id=customer_id,
            franchise_id=franchise_id,
            registration_number=registration_number,
            vehicle_type=vehicle_type,
            color=color,
            model=model,
        )
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    else:
        return success_response(
            message="Vehicles fetched successfully.",
            data=serialize_vehicle_list_response(db, vehicles),
            status_code=status.HTTP_200_OK,
        )


@vehicles_router.get("/{vehicle_id}")
def get_vehicle(
        vehicle_id: int,
        context: UserContext = Depends(require_permissions(VIEW_VEHICLES)),
        db: Session = Depends(get_db),
) -> dict:
    """Vehicle detail. **Path:** `vehicle_id`. **Auth:** `VIEW_VEHICLES`. **Success:** 200. **Errors:** AppError. 422 / 500.
    """
    try:
        vehicle = get_vehicle_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            vehicle_id=vehicle_id,
        )
        data = serialize_vehicle_detail_response(db, vehicle)
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    else:
        return success_response(
            message=("Vehicle fetched successfully."
                     if data is not None else "No vehicle returned."),
            data=data,
            status_code=status.HTTP_200_OK,
        )


@vehicles_router.post("")
def create_vehicle(
        payload: VehicleCreateRequest,
        context: UserContext = Depends(require_permissions(CREATE_VEHICLES)),
        db: Session = Depends(get_db),
) -> dict:
    """Create vehicle. **Body:** `VehicleCreateRequest`. **Auth:** `CREATE_VEHICLES`. **Success:** 201. **Errors:** AppError. 422 / 500.
    """
    try:
        vehicle = create_vehicle_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            customer_id=payload.customer_id,
            franchise_id=payload.franchise_id,
            name=payload.name,
            registration_number=payload.registration_number,
            colour=payload.colour,
            model=payload.model,
            vehicle_type=payload.vehicle_type,
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
            message="Vehicle created successfully.",
            data=serialize_vehicle_row(vehicle),
            status_code=status.HTTP_201_CREATED,
        )


@vehicles_router.patch("/{vehicle_id}")
def patch_vehicle(
        vehicle_id: int,
        payload: VehiclePatchRequest,
        context: UserContext = Depends(require_permissions(UPDATE_VEHICLES)),
        db: Session = Depends(get_db),
) -> dict:
    """Partial update. **Body:** `VehiclePatchRequest`. **Auth:** `UPDATE_VEHICLES`. **Success:** 200. **Errors:** AppError. 422 / 500.
    """
    try:
        vehicle = update_vehicle_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            vehicle_id=vehicle_id,
            name=payload.name,
            vehicle_type=payload.vehicle_type,
            colour=payload.colour,
            model=payload.model,
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
            message="Vehicle updated successfully.",
            data=serialize_vehicle_patch_response(vehicle),
            status_code=status.HTTP_200_OK,
        )


@vehicles_router.delete("/{vehicle_id}")
def delete_vehicle(
        vehicle_id: int,
        context: UserContext = Depends(require_permissions(DELETE_VEHICLES)),
        db: Session = Depends(get_db),
) -> dict:
    """Soft-delete a vehicle and its booking / invoice / payment tree."""
    try:
        vehicle = soft_delete_vehicle_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            vehicle_id=vehicle_id,
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
            message="Vehicle deleted successfully.",
            data={
                "id": vehicle.id,
                "is_deleted": vehicle.is_deleted,
                "updated_at": str(vehicle.updated_at),
            },
            status_code=status.HTTP_200_OK,
        )
