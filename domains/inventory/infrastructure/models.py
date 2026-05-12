from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from foundation.database.base import Base


class InventoryItem(Base):
    __tablename__ = "inventory_items"
    __table_args__ = (
        Index(
            "uq_inventory_items_active_name",
            "name",
            unique=True,
            postgresql_where=text("is_deleted IS FALSE"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class ServiceInventoryItemUsage(Base):
    __tablename__ = "service_inventory_item_usages"
    __table_args__ = (
        Index(
            "uq_service_inventory_item_usage_active_pair",
            "service_id",
            "inventory_item_id",
            unique=True,
            postgresql_where=text("is_deleted IS FALSE"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    inventory_item_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_items.id"),
        index=True,
    )
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), index=True)
    quantity_required: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class FranchiseInventory(Base):
    __tablename__ = "franchise_inventory"
    __table_args__ = (
        Index(
            "uq_franchise_inventory_active_pair",
            "franchise_id",
            "inventory_item_id",
            unique=True,
            postgresql_where=text("is_deleted IS FALSE"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    franchise_id: Mapped[int] = mapped_column(
        ForeignKey("franchises.id"),
        index=True,
    )
    inventory_item_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_items.id"),
        index=True,
    )
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        default=Decimal("0.0000"),
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
