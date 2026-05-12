"""HTTP/API response shapes for inventory domain entities."""

from __future__ import annotations

from domains.inventory.infrastructure.models import InventoryItem
from domains.inventory.infrastructure.models import FranchiseInventory
from domains.inventory.infrastructure.models import ServiceInventoryItemUsage


def serialize_inventory_item_row(item: InventoryItem) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "description": item.description,
        "created_at": str(item.created_at),
        "updated_at": str(item.updated_at),
    }


def serialize_inventory_item_patch_response(item: InventoryItem) -> dict:
    return {
        "id": item.id,
        "updated_at": str(item.updated_at),
    }


def serialize_inventory_item_delete_response(item: InventoryItem) -> dict:
    return {
        "id": item.id,
        "is_deleted": item.is_deleted,
        "updated_at": str(item.updated_at),
    }


def serialize_service_inventory_item_usage_row(
        usage: ServiceInventoryItemUsage) -> dict:
    return {
        "id": usage.id,
        "inventory_item_id": usage.inventory_item_id,
        "service_id": usage.service_id,
        "quantity_required": str(usage.quantity_required),
        "created_at": str(usage.created_at),
        "updated_at": str(usage.updated_at),
    }


def serialize_service_inventory_item_usage_patch_response(
        usage: ServiceInventoryItemUsage) -> dict:
    return {
        "id": usage.id,
        "updated_at": str(usage.updated_at),
    }


def serialize_service_inventory_item_usage_delete_response(
        usage: ServiceInventoryItemUsage) -> dict:
    return {
        "id": usage.id,
        "is_deleted": usage.is_deleted,
        "updated_at": str(usage.updated_at),
    }


def serialize_franchise_inventory_row(stock: FranchiseInventory) -> dict:
    return {
        "id": stock.id,
        "franchise_id": stock.franchise_id,
        "inventory_item_id": stock.inventory_item_id,
        "quantity": str(stock.quantity),
        "created_at": str(stock.created_at),
        "updated_at": str(stock.updated_at),
    }


def serialize_franchise_inventory_add_stock_response(
        stock: FranchiseInventory, *, old_quantity: str,
        quantity_added: str) -> dict:
    return {
        "id": stock.id,
        "franchise_id": stock.franchise_id,
        "inventory_item_id": stock.inventory_item_id,
        "old_quantity": old_quantity,
        "quantity_added": quantity_added,
        "new_quantity": str(stock.quantity),
        "updated_at": str(stock.updated_at),
    }


def serialize_franchise_inventory_set_stock_response(
        stock: FranchiseInventory, *, old_quantity: str) -> dict:
    return {
        "id": stock.id,
        "franchise_id": stock.franchise_id,
        "inventory_item_id": stock.inventory_item_id,
        "old_quantity": old_quantity,
        "new_quantity": str(stock.quantity),
        "updated_at": str(stock.updated_at),
    }
