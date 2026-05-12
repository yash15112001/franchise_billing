from __future__ import annotations

from decimal import Decimal

from fastapi import status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from domains.audit.application.service import write_audit_log
from domains.bookings.domain.enums import BookingServiceStatus
from domains.bookings.infrastructure.models import Booking, BookingItem
from domains.catalog.infrastructure.models import Service
from domains.franchises.infrastructure.models import Franchise
from domains.inventory.infrastructure.models import (
    FranchiseInventory,
    InventoryItem,
    ServiceInventoryItemUsage,
)
from domains.users.domain.access import UserRole
from domains.users.infrastructure.models import User
from foundation.errors import AppError

_ZERO = Decimal("0.0000")


def _optional_query_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _quantity_4(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"))


def _require_actor_franchise_id(actor_role: UserRole,
                                actor_franchise_id: int | None) -> int:
    if actor_role is UserRole.MAIN_ADMIN:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Actor franchise resolution is not needed for main admin.",
            error_code="INVALID_MAIN_ADMIN_FRANCHISE_RESOLUTION",
        )
    if actor_franchise_id is None:
        raise AppError(
            status_code=status.HTTP_403_FORBIDDEN,
            message="Franchise context is required.",
            error_code="MISSING_FRANCHISE_CONTEXT",
        )
    return actor_franchise_id


def list_inventory_items(
    db: Session,
    *,
    search: str | None = None,
    name: str | None = None,
) -> list[InventoryItem]:
    search = _optional_query_text(search)
    name = _optional_query_text(name)

    statement = select(InventoryItem).where(
        InventoryItem.is_deleted.is_(False)).order_by(InventoryItem.id.asc())

    if name:
        statement = statement.where(InventoryItem.name.ilike(f"%{name}%"))
    if search:
        query = f"%{search}%"
        statement = statement.where(
            or_(
                InventoryItem.name.ilike(query),
                InventoryItem.description.ilike(query),
            ))

    return list(db.scalars(statement).all())


def get_inventory_item_by_id(
    db: Session,
    *,
    inventory_item_id: int,
) -> InventoryItem:
    item = db.scalar(
        select(InventoryItem).where(
            InventoryItem.id == inventory_item_id,
            InventoryItem.is_deleted.is_(False),
        ))
    if item is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Inventory item not found.",
            error_code="INVENTORY_ITEM_NOT_FOUND",
            details={"inventory_item_id": inventory_item_id},
        )
    return item


def _get_active_service_by_id(
    db: Session,
    *,
    service_id: int,
) -> Service:
    service = db.scalar(
        select(Service).where(
            Service.id == service_id,
            Service.is_active.is_(True),
        ))
    if service is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Service not found.",
            error_code="SERVICE_NOT_FOUND",
            details={"service_id": service_id},
        )
    return service


def _ensure_service_inventory_mapping_mutable(
    db: Session,
    *,
    service_id: int,
) -> None:
    active_booking_item_ids = list(
        db.scalars(
            select(BookingItem.id).join(
                Booking,
                BookingItem.booking_id == Booking.id,
            ).where(
                BookingItem.service_id == service_id,
                BookingItem.is_deleted.is_(False),
                Booking.is_deleted.is_(False),
                Booking.service_status.not_in(
                    (
                        BookingServiceStatus.COMPLETE,
                        BookingServiceStatus.CANCELLED,
                    )),
            )).all())
    if active_booking_item_ids:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            message=("This service-inventory mapping cannot be modified while "
                     "there are active bookings using the service."),
            error_code="SERVICE_INVENTORY_ITEM_USAGE_IN_USE",
            details={
                "service_id": service_id,
                "active_booking_item_count": len(active_booking_item_ids),
                "active_booking_item_ids": active_booking_item_ids,
            },
        )


def create_inventory_item_for_actor(
    db: Session,
    *,
    actor: User,
    name: str,
    description: str | None,
) -> InventoryItem:
    item = InventoryItem(
        name=name,
        description=description,
        is_deleted=False,
    )
    db.add(item)

    try:
        db.flush()
    except IntegrityError as exc:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            message="An active inventory item with the same name already exists.",
            error_code="DUPLICATE_ACTIVE_INVENTORY_ITEM",
            details={"name": name},
        ) from exc

    franchise_ids = db.scalars(
        select(Franchise.id).where(Franchise.is_deleted.is_(False)).order_by(
            Franchise.id.asc())).all()
    for franchise_id in franchise_ids:
        db.add(
            FranchiseInventory(
                franchise_id=franchise_id,
                inventory_item_id=item.id,
                quantity=_ZERO,
                is_deleted=False,
            ))
    db.flush()

    write_audit_log(
        db,
        action="inventory_item.create",
        entity_name="inventory_items",
        entity_id=str(item.id),
        actor_user_id=actor.id,
        franchise_id=None,
        payload={
            "name": item.name,
            "description": item.description,
        },
    )
    return item


def patch_inventory_item_for_actor(
    db: Session,
    *,
    actor: User,
    inventory_item_id: int,
    has_name: bool,
    name: str | None,
    has_description: bool,
    description: str | None,
) -> InventoryItem:
    item = get_inventory_item_by_id(db, inventory_item_id=inventory_item_id)

    if not has_name and not has_description:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="At least one field must be provided for update.",
            error_code="EMPTY_INVENTORY_ITEM_PATCH",
            details={"inventory_item_id": inventory_item_id},
        )

    if has_name and name is not None:
        item.name = name
    if has_description:
        item.description = description

    try:
        db.flush()
    except IntegrityError as exc:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            message="An active inventory item with the same name already exists.",
            error_code="DUPLICATE_ACTIVE_INVENTORY_ITEM",
            details={"name": item.name},
        ) from exc

    write_audit_log(
        db,
        action="inventory_item.update",
        entity_name="inventory_items",
        entity_id=str(item.id),
        actor_user_id=actor.id,
        franchise_id=None,
        payload={
            "name": item.name,
            "description": item.description,
        },
    )
    return item


def soft_delete_inventory_item_for_actor(
    db: Session,
    *,
    actor: User,
    inventory_item_id: int,
) -> InventoryItem:
    item = get_inventory_item_by_id(db, inventory_item_id=inventory_item_id)

    usage_rows = db.scalars(
        select(ServiceInventoryItemUsage).where(
            ServiceInventoryItemUsage.inventory_item_id == item.id,
            ServiceInventoryItemUsage.is_deleted.is_(False),
        )).all()
    if usage_rows:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            message=("Inventory item cannot be deleted while it is mapped to "
                     "one or more services."),
            error_code="INVENTORY_ITEM_IN_USE",
            details={
                "inventory_item_id": item.id,
                "active_service_mapping_count": len(usage_rows),
                "service_inventory_item_usage_ids": [row.id for row in usage_rows],
            },
        )

    item.is_deleted = True
    stock_rows = db.scalars(
        select(FranchiseInventory).where(
            FranchiseInventory.inventory_item_id == item.id,
            FranchiseInventory.is_deleted.is_(False),
        )).all()
    for stock_row in stock_rows:
        stock_row.is_deleted = True

    db.flush()
    write_audit_log(
        db,
        action="inventory_item.delete",
        entity_name="inventory_items",
        entity_id=str(item.id),
        actor_user_id=actor.id,
        franchise_id=None,
        payload={
            "name": item.name,
            "franchise_inventory_ids": [row.id for row in stock_rows],
        },
    )
    return item


def list_service_inventory_item_usages(
    db: Session,
    *,
    service_id: int | None = None,
    inventory_item_id: int | None = None,
) -> list[ServiceInventoryItemUsage]:
    statement = select(ServiceInventoryItemUsage).where(
        ServiceInventoryItemUsage.is_deleted.is_(False)).order_by(
            ServiceInventoryItemUsage.id.asc())

    if service_id is not None:
        statement = statement.where(
            ServiceInventoryItemUsage.service_id == service_id)
    if inventory_item_id is not None:
        statement = statement.where(
            ServiceInventoryItemUsage.inventory_item_id == inventory_item_id)

    return list(db.scalars(statement).all())


def get_service_inventory_item_usage_by_id(
    db: Session,
    *,
    service_inventory_item_usage_id: int,
) -> ServiceInventoryItemUsage:
    usage = db.scalar(
        select(ServiceInventoryItemUsage).where(
            ServiceInventoryItemUsage.id == service_inventory_item_usage_id,
            ServiceInventoryItemUsage.is_deleted.is_(False),
        ))
    if usage is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Service inventory item usage not found.",
            error_code="SERVICE_INVENTORY_ITEM_USAGE_NOT_FOUND",
            details={
                "service_inventory_item_usage_id":
                service_inventory_item_usage_id
            },
        )
    return usage


def create_service_inventory_item_usage_for_actor(
    db: Session,
    *,
    actor: User,
    service_id: int,
    inventory_item_id: int,
    quantity_required: Decimal,
) -> ServiceInventoryItemUsage:
    _get_active_service_by_id(db, service_id=service_id)
    get_inventory_item_by_id(db, inventory_item_id=inventory_item_id)

    usage = ServiceInventoryItemUsage(
        service_id=service_id,
        inventory_item_id=inventory_item_id,
        quantity_required=_quantity_4(quantity_required),
        is_deleted=False,
    )
    db.add(usage)

    try:
        db.flush()
    except IntegrityError as exc:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            message=("This inventory item is already mapped to the specified "
                     "service."),
            error_code="DUPLICATE_SERVICE_INVENTORY_ITEM_USAGE",
            details={
                "service_id": service_id,
                "inventory_item_id": inventory_item_id,
            },
        ) from exc

    write_audit_log(
        db,
        action="service_inventory_item_usage.create",
        entity_name="service_inventory_item_usages",
        entity_id=str(usage.id),
        actor_user_id=actor.id,
        franchise_id=None,
        payload={
            "service_id": usage.service_id,
            "inventory_item_id": usage.inventory_item_id,
            "quantity_required": str(usage.quantity_required),
        },
    )
    return usage


def patch_service_inventory_item_usage_for_actor(
    db: Session,
    *,
    actor: User,
    service_inventory_item_usage_id: int,
    quantity_required: Decimal,
) -> ServiceInventoryItemUsage:
    usage = get_service_inventory_item_usage_by_id(
        db,
        service_inventory_item_usage_id=service_inventory_item_usage_id,
    )
    _ensure_service_inventory_mapping_mutable(db, service_id=usage.service_id)

    normalized_quantity = _quantity_4(quantity_required)
    if normalized_quantity <= _ZERO:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Quantity required must be greater than zero.",
            error_code="INVALID_QUANTITY_REQUIRED",
            details={
                "service_inventory_item_usage_id":
                service_inventory_item_usage_id
            },
        )

    usage.quantity_required = normalized_quantity
    db.flush()

    write_audit_log(
        db,
        action="service_inventory_item_usage.update",
        entity_name="service_inventory_item_usages",
        entity_id=str(usage.id),
        actor_user_id=actor.id,
        franchise_id=None,
        payload={
            "service_id": usage.service_id,
            "inventory_item_id": usage.inventory_item_id,
            "quantity_required": str(usage.quantity_required),
        },
    )
    return usage


def soft_delete_service_inventory_item_usage_for_actor(
    db: Session,
    *,
    actor: User,
    service_inventory_item_usage_id: int,
) -> ServiceInventoryItemUsage:
    usage = get_service_inventory_item_usage_by_id(
        db,
        service_inventory_item_usage_id=service_inventory_item_usage_id,
    )
    _ensure_service_inventory_mapping_mutable(db, service_id=usage.service_id)
    usage.is_deleted = True
    db.flush()

    write_audit_log(
        db,
        action="service_inventory_item_usage.delete",
        entity_name="service_inventory_item_usages",
        entity_id=str(usage.id),
        actor_user_id=actor.id,
        franchise_id=None,
        payload={
            "service_id": usage.service_id,
            "inventory_item_id": usage.inventory_item_id,
        },
    )
    return usage


def list_franchise_inventory_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    franchise_id: int | None,
    inventory_item_id: int | None,
) -> list[FranchiseInventory]:
    statement = select(FranchiseInventory).where(
        FranchiseInventory.is_deleted.is_(False)).order_by(
            FranchiseInventory.id.asc())

    if actor_role is UserRole.MAIN_ADMIN:
        if franchise_id is not None:
            statement = statement.where(
                FranchiseInventory.franchise_id == franchise_id)
    else:
        resolved_franchise_id = _require_actor_franchise_id(
            actor_role, actor_franchise_id)
        if franchise_id is not None and franchise_id != resolved_franchise_id:
            # Match the looser list-scope pattern used elsewhere: ignore foreign filter.
            pass
        statement = statement.where(
            FranchiseInventory.franchise_id == resolved_franchise_id)

    if inventory_item_id is not None:
        statement = statement.where(
            FranchiseInventory.inventory_item_id == inventory_item_id)

    return list(db.scalars(statement).all())


def get_franchise_inventory_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    franchise_inventory_id: int,
) -> FranchiseInventory:
    statement = select(FranchiseInventory).where(
        FranchiseInventory.id == franchise_inventory_id,
        FranchiseInventory.is_deleted.is_(False),
    )

    if actor_role is not UserRole.MAIN_ADMIN:
        resolved_franchise_id = _require_actor_franchise_id(
            actor_role, actor_franchise_id)
        statement = statement.where(
            FranchiseInventory.franchise_id == resolved_franchise_id)

    stock = db.scalar(statement)
    if stock is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Franchise inventory record not found.",
            error_code="FRANCHISE_INVENTORY_NOT_FOUND",
            details={"franchise_inventory_id": franchise_inventory_id},
        )
    return stock


def add_franchise_inventory_stock_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    franchise_inventory_id: int,
    quantity_to_be_added: Decimal,
) -> tuple[FranchiseInventory, str, str]:
    if actor_role not in (UserRole.MAIN_ADMIN, UserRole.FRANCHISE_ADMIN):
        raise AppError(
            status_code=status.HTTP_403_FORBIDDEN,
            message="Only main admin or franchise admin can add stock.",
            error_code="FORBIDDEN_FRANCHISE_INVENTORY_STOCK_UPDATE",
        )

    stock = get_franchise_inventory_for_actor(
        db,
        actor=actor,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        franchise_inventory_id=franchise_inventory_id,
    )

    normalized_add = _quantity_4(quantity_to_be_added)
    if normalized_add <= _ZERO:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Quantity to be added must be greater than zero.",
            error_code="INVALID_STOCK_ADDITION_QUANTITY",
            details={"franchise_inventory_id": franchise_inventory_id},
        )

    old_quantity = str(stock.quantity)
    stock.quantity = _quantity_4(stock.quantity + normalized_add)
    db.flush()

    write_audit_log(
        db,
        action="franchise_inventory.add_stock",
        entity_name="franchise_inventory",
        entity_id=str(stock.id),
        actor_user_id=actor.id,
        franchise_id=stock.franchise_id,
        payload={
            "inventory_item_id": stock.inventory_item_id,
            "old_quantity": old_quantity,
            "quantity_added": str(normalized_add),
            "new_quantity": str(stock.quantity),
        },
    )
    return stock, old_quantity, str(normalized_add)


def set_franchise_inventory_stock_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    franchise_inventory_id: int,
    quantity: Decimal,
) -> tuple[FranchiseInventory, str]:
    if actor_role not in (UserRole.MAIN_ADMIN, UserRole.FRANCHISE_ADMIN):
        raise AppError(
            status_code=status.HTTP_403_FORBIDDEN,
            message="Only main admin or franchise admin can set stock.",
            error_code="FORBIDDEN_FRANCHISE_INVENTORY_STOCK_UPDATE",
        )

    stock = get_franchise_inventory_for_actor(
        db,
        actor=actor,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        franchise_inventory_id=franchise_inventory_id,
    )

    normalized_quantity = _quantity_4(quantity)
    if normalized_quantity < _ZERO:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Quantity can not be negative.",
            error_code="INVALID_STOCK_SET_QUANTITY",
            details={"franchise_inventory_id": franchise_inventory_id},
        )

    old_quantity = str(stock.quantity)
    stock.quantity = normalized_quantity
    db.flush()

    write_audit_log(
        db,
        action="franchise_inventory.set_stock",
        entity_name="franchise_inventory",
        entity_id=str(stock.id),
        actor_user_id=actor.id,
        franchise_id=stock.franchise_id,
        payload={
            "inventory_item_id": stock.inventory_item_id,
            "old_quantity": old_quantity,
            "new_quantity": str(stock.quantity),
        },
    )
    return stock, old_quantity
