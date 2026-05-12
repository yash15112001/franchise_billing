"""Inventory HTTP APIs (inventory items implemented; others pending)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from starlette import status

from domains.inventory.application.service import (
    add_franchise_inventory_stock_for_actor,
    create_inventory_item_for_actor,
    create_service_inventory_item_usage_for_actor,
    get_franchise_inventory_for_actor,
    get_inventory_item_by_id,
    get_service_inventory_item_usage_by_id,
    list_franchise_inventory_for_actor,
    list_inventory_items as list_inventory_items_service,
    list_service_inventory_item_usages as list_service_inventory_item_usages_service,
    patch_inventory_item_for_actor,
    patch_service_inventory_item_usage_for_actor,
    set_franchise_inventory_stock_for_actor,
    soft_delete_inventory_item_for_actor,
    soft_delete_service_inventory_item_usage_for_actor,
)
from domains.inventory.interfaces.serializers import (
    serialize_franchise_inventory_add_stock_response,
    serialize_franchise_inventory_row,
    serialize_franchise_inventory_set_stock_response,
    serialize_inventory_item_delete_response,
    serialize_inventory_item_patch_response,
    serialize_inventory_item_row,
    serialize_service_inventory_item_usage_delete_response,
    serialize_service_inventory_item_usage_patch_response,
    serialize_service_inventory_item_usage_row,
)
from domains.inventory.interfaces.schemas import (
    AddFranchiseInventoryStockRequest,
    InventoryItemCreateRequest,
    InventoryItemPatchRequest,
    SetFranchiseInventoryStockRequest,
    ServiceInventoryItemUsageCreateRequest,
    ServiceInventoryItemUsagePatchRequest,
)
from domains.users.domain.access import (
    ADD_FRANCHISE_INVENTORY_STOCK,
    CREATE_INVENTORY_ITEMS,
    CREATE_SERVICE_INVENTORY_ITEM_USAGES,
    DELETE_INVENTORY_ITEMS,
    DELETE_SERVICE_INVENTORY_ITEM_USAGES,
    SET_FRANCHISE_INVENTORY_STOCK,
    UPDATE_INVENTORY_ITEMS,
    UPDATE_SERVICE_INVENTORY_ITEM_USAGES,
    VIEW_FRANCHISE_INVENTORY,
    VIEW_INVENTORY_ITEMS,
    VIEW_SERVICE_INVENTORY_ITEM_USAGES,
)
from foundation.database.session import get_db
from foundation.errors import AppError
from foundation.web.dependencies import UserContext, require_permissions
from foundation.web.responses import error_response, internal_error_response, success_response

inventory_items_router = APIRouter(prefix="/inventory-items",
                                   tags=["inventory-items"])
service_inventory_item_usages_router = APIRouter(
    prefix="/service-inventory-item-usages",
    tags=["service-inventory-item-usages"],
)
franchise_inventory_router = APIRouter(prefix="/franchise-inventory",
                                       tags=["franchise-inventory"])

_CONTRACT = "docs/architecture/api_contracts.txt"


def _not_implemented(section: str) -> None:
    raise AppError(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        message=f"Not implemented. See {_CONTRACT} ({section}).",
        error_code="NOT_IMPLEMENTED",
    )


@inventory_items_router.get("")
def list_inventory_items(
    search: str | None = Query(default=None),
    name: str | None = Query(default=None),
    _context: UserContext = Depends(require_permissions(VIEW_INVENTORY_ITEMS)),
    db: Session = Depends(get_db),
) -> dict:
    try:
        items = list_inventory_items_service(db, search=search, name=name)
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    return success_response(
        message="Inventory items fetched successfully.",
        data=[serialize_inventory_item_row(item) for item in items],
        status_code=status.HTTP_200_OK,
    )


@inventory_items_router.get("/{inventory_item_id}")
def get_inventory_item(
    inventory_item_id: int,
    _context: UserContext = Depends(require_permissions(VIEW_INVENTORY_ITEMS)),
    db: Session = Depends(get_db),
) -> dict:
    try:
        item = get_inventory_item_by_id(db, inventory_item_id=inventory_item_id)
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    return success_response(
        message="Inventory item fetched successfully.",
        data=serialize_inventory_item_row(item),
        status_code=status.HTTP_200_OK,
    )


@inventory_items_router.post("")
def create_inventory_item(
    payload: InventoryItemCreateRequest,
    context: UserContext = Depends(require_permissions(CREATE_INVENTORY_ITEMS)),
    db: Session = Depends(get_db),
) -> dict:
    try:
        item = create_inventory_item_for_actor(
            db,
            actor=context.user,
            name=payload.name,
            description=payload.description,
        )
        db.commit()
    except AppError as exc:
        db.rollback()
        return error_response(exc)
    except Exception:
        db.rollback()
        return internal_error_response()
    return success_response(
        message="Inventory item created successfully.",
        data=serialize_inventory_item_row(item),
        status_code=status.HTTP_201_CREATED,
    )


@inventory_items_router.patch("/{inventory_item_id}")
def patch_inventory_item(
    inventory_item_id: int,
    payload: InventoryItemPatchRequest,
    context: UserContext = Depends(require_permissions(UPDATE_INVENTORY_ITEMS)),
    db: Session = Depends(get_db),
) -> dict:
    provided_fields = payload.model_fields_set
    try:
        item = patch_inventory_item_for_actor(
            db,
            actor=context.user,
            inventory_item_id=inventory_item_id,
            has_name="name" in provided_fields,
            name=payload.name,
            has_description="description" in provided_fields,
            description=payload.description,
        )
        db.commit()
    except AppError as exc:
        db.rollback()
        return error_response(exc)
    except Exception:
        db.rollback()
        return internal_error_response()
    return success_response(
        message="Inventory item updated successfully.",
        data=serialize_inventory_item_patch_response(item),
        status_code=status.HTTP_200_OK,
    )


@inventory_items_router.delete("/{inventory_item_id}")
def delete_inventory_item(
    inventory_item_id: int,
    context: UserContext = Depends(require_permissions(DELETE_INVENTORY_ITEMS)),
    db: Session = Depends(get_db),
) -> dict:
    try:
        item = soft_delete_inventory_item_for_actor(
            db,
            actor=context.user,
            inventory_item_id=inventory_item_id,
        )
        db.commit()
    except AppError as exc:
        db.rollback()
        return error_response(exc)
    except Exception:
        db.rollback()
        return internal_error_response()
    return success_response(
        message="Inventory item deleted successfully.",
        data=serialize_inventory_item_delete_response(item),
        status_code=status.HTTP_200_OK,
    )


@service_inventory_item_usages_router.get("")
def list_service_inventory_item_usages(
    service_id: int | None = Query(default=None),
    inventory_item_id: int | None = Query(default=None),
    _context: UserContext = Depends(
        require_permissions(VIEW_SERVICE_INVENTORY_ITEM_USAGES)),
    db: Session = Depends(get_db),
) -> dict:
    try:
        usages = list_service_inventory_item_usages_service(
            db,
            service_id=service_id,
            inventory_item_id=inventory_item_id,
        )
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    return success_response(
        message="Service inventory item usages fetched successfully.",
        data=[
            serialize_service_inventory_item_usage_row(usage)
            for usage in usages
        ],
        status_code=status.HTTP_200_OK,
    )


@service_inventory_item_usages_router.get("/{service_inventory_item_usage_id}")
def get_service_inventory_item_usage(
    service_inventory_item_usage_id: int,
    _context: UserContext = Depends(
        require_permissions(VIEW_SERVICE_INVENTORY_ITEM_USAGES)),
    db: Session = Depends(get_db),
) -> dict:
    try:
        usage = get_service_inventory_item_usage_by_id(
            db,
            service_inventory_item_usage_id=service_inventory_item_usage_id,
        )
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    return success_response(
        message="Service inventory item usage fetched successfully.",
        data=serialize_service_inventory_item_usage_row(usage),
        status_code=status.HTTP_200_OK,
    )


@service_inventory_item_usages_router.post("")
def create_service_inventory_item_usage(
    payload: ServiceInventoryItemUsageCreateRequest,
    context: UserContext = Depends(
        require_permissions(CREATE_SERVICE_INVENTORY_ITEM_USAGES)),
    db: Session = Depends(get_db),
) -> dict:
    try:
        usage = create_service_inventory_item_usage_for_actor(
            db,
            actor=context.user,
            service_id=payload.service_id,
            inventory_item_id=payload.inventory_item_id,
            quantity_required=payload.quantity_required,
        )
        db.commit()
    except AppError as exc:
        db.rollback()
        return error_response(exc)
    except Exception:
        db.rollback()
        return internal_error_response()
    return success_response(
        message="Service inventory item usage created successfully.",
        data=serialize_service_inventory_item_usage_row(usage),
        status_code=status.HTTP_201_CREATED,
    )


@service_inventory_item_usages_router.patch(
    "/{service_inventory_item_usage_id}")
def patch_service_inventory_item_usage(
    service_inventory_item_usage_id: int,
    payload: ServiceInventoryItemUsagePatchRequest,
    context: UserContext = Depends(
        require_permissions(UPDATE_SERVICE_INVENTORY_ITEM_USAGES)),
    db: Session = Depends(get_db),
) -> dict:
    try:
        usage = patch_service_inventory_item_usage_for_actor(
            db,
            actor=context.user,
            service_inventory_item_usage_id=service_inventory_item_usage_id,
            quantity_required=payload.quantity_required,
        )
        db.commit()
    except AppError as exc:
        db.rollback()
        return error_response(exc)
    except Exception:
        db.rollback()
        return internal_error_response()
    return success_response(
        message="Service inventory item usage updated successfully.",
        data=serialize_service_inventory_item_usage_patch_response(usage),
        status_code=status.HTTP_200_OK,
    )


@service_inventory_item_usages_router.delete(
    "/{service_inventory_item_usage_id}")
def delete_service_inventory_item_usage(
    service_inventory_item_usage_id: int,
    context: UserContext = Depends(
        require_permissions(DELETE_SERVICE_INVENTORY_ITEM_USAGES)),
    db: Session = Depends(get_db),
) -> dict:
    try:
        usage = soft_delete_service_inventory_item_usage_for_actor(
            db,
            actor=context.user,
            service_inventory_item_usage_id=service_inventory_item_usage_id,
        )
        db.commit()
    except AppError as exc:
        db.rollback()
        return error_response(exc)
    except Exception:
        db.rollback()
        return internal_error_response()
    return success_response(
        message="Service inventory item usage deleted successfully.",
        data=serialize_service_inventory_item_usage_delete_response(usage),
        status_code=status.HTTP_200_OK,
    )


@franchise_inventory_router.get("")
def list_franchise_inventory(
    franchise_id: int | None = Query(default=None),
    inventory_item_id: int | None = Query(default=None),
    context: UserContext = Depends(
        require_permissions(VIEW_FRANCHISE_INVENTORY)),
    db: Session = Depends(get_db),
) -> dict:
    try:
        rows = list_franchise_inventory_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            franchise_id=franchise_id,
            inventory_item_id=inventory_item_id,
        )
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    return success_response(
        message="Franchise inventory fetched successfully.",
        data=[serialize_franchise_inventory_row(row) for row in rows],
        status_code=status.HTTP_200_OK,
    )


@franchise_inventory_router.get("/{franchise_inventory_id}")
def get_franchise_inventory(
    franchise_inventory_id: int,
    context: UserContext = Depends(
        require_permissions(VIEW_FRANCHISE_INVENTORY)),
    db: Session = Depends(get_db),
) -> dict:
    try:
        row = get_franchise_inventory_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            franchise_inventory_id=franchise_inventory_id,
        )
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    return success_response(
        message="Franchise inventory record fetched successfully.",
        data=serialize_franchise_inventory_row(row),
        status_code=status.HTTP_200_OK,
    )


@franchise_inventory_router.patch("/{franchise_inventory_id}/add-stock")
def add_franchise_inventory_stock(
    franchise_inventory_id: int,
    payload: AddFranchiseInventoryStockRequest,
    context: UserContext = Depends(
        require_permissions(ADD_FRANCHISE_INVENTORY_STOCK)),
    db: Session = Depends(get_db),
) -> dict:
    try:
        row, old_quantity, quantity_added = (
            add_franchise_inventory_stock_for_actor(
                db,
                actor=context.user,
                actor_role=context.role,
                actor_franchise_id=context.franchise_id,
                franchise_inventory_id=franchise_inventory_id,
                quantity_to_be_added=payload.quantity_to_be_added,
            ))
        db.commit()
    except AppError as exc:
        db.rollback()
        return error_response(exc)
    except Exception:
        db.rollback()
        return internal_error_response()
    return success_response(
        message="Franchise inventory stock added successfully.",
        data=serialize_franchise_inventory_add_stock_response(
            row,
            old_quantity=old_quantity,
            quantity_added=quantity_added,
        ),
        status_code=status.HTTP_200_OK,
    )


@franchise_inventory_router.patch("/{franchise_inventory_id}/set-stock")
def set_franchise_inventory_stock(
    franchise_inventory_id: int,
    payload: SetFranchiseInventoryStockRequest,
    context: UserContext = Depends(
        require_permissions(SET_FRANCHISE_INVENTORY_STOCK)),
    db: Session = Depends(get_db),
) -> dict:
    try:
        row, old_quantity = set_franchise_inventory_stock_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            franchise_inventory_id=franchise_inventory_id,
            quantity=payload.quantity,
        )
        db.commit()
    except AppError as exc:
        db.rollback()
        return error_response(exc)
    except Exception:
        db.rollback()
        return internal_error_response()
    return success_response(
        message="Franchise inventory stock set successfully.",
        data=serialize_franchise_inventory_set_stock_response(
            row,
            old_quantity=old_quantity,
        ),
        status_code=status.HTTP_200_OK,
    )
