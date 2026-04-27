from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, time, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    event,
    func,
    update,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from domains.franchises.domain.enums import DayOfWeek, FranchiseStatus
from foundation.database.base import Base

logger = logging.getLogger(__name__)


def new_franchise_code_placeholder() -> str:
    """Unique value for ``Franchise.code`` on insert; replaced in DB by ``after_insert``."""
    return f"FR-{uuid.uuid4().hex}"


def format_franchise_code(franchise_id: int) -> str:
    """Deterministic display code: ``FR-`` + zero-padded primary key."""
    return f"FR-{franchise_id:04d}"


class Franchise(Base):
    __tablename__ = "franchises"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    address: Mapped[str] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(80), index=True)
    state: Mapped[str] = mapped_column(String(80), index=True)
    pincode: Mapped[str] = mapped_column(String(6), index=True)
    country: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[FranchiseStatus] = mapped_column(
        SqlEnum(
            FranchiseStatus,
            name="franchise_status",
            native_enum=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        index=True,
    )
    gst_number: Mapped[str] = mapped_column(String(32))
    pan_number: Mapped[str] = mapped_column(String(20))
    monthly_target: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    location_url: Mapped[str | None] = mapped_column(String(512),
                                                     nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    commission_policies: Mapped[list["CommissionPolicy"]] = relationship(
        back_populates="franchise", )
    timings: Mapped[list["FranchiseTiming"]] = relationship(
        back_populates="franchise", )
    reviews: Mapped[list["FranchiseReview"]] = relationship(
        back_populates="franchise", )


@event.listens_for(Franchise, "after_insert")
def _set_franchise_code_after_insert(mapper, connection,
                                     target: Franchise) -> None:
    """Replace placeholder ``code`` with ``FR-{id}`` once the row has an id."""
    if target.id is None:
        return
    desired = format_franchise_code(target.id)
    if target.code == desired:
        return
    connection.execute(
        update(Franchise.__table__).where(
            Franchise.__table__.c.id == target.id).values(code=desired), )
    target.code = desired


class CommissionPolicy(Base):
    __tablename__ = "franchise_commission_policies"

    id: Mapped[int] = mapped_column(primary_key=True)
    franchise_id: Mapped[int] = mapped_column(
        ForeignKey("franchises.id"),
        index=True,
    )
    percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    effective_from: Mapped[date] = mapped_column(Date, index=True)
    effective_till: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
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

    franchise: Mapped[Franchise] = relationship(
        back_populates="commission_policies")


class FranchiseTiming(Base):
    __tablename__ = "franchise_timings"
    __table_args__ = (UniqueConstraint(
        "franchise_id",
        "day_of_week",
        name="uq_franchise_timing_day",
    ), )

    id: Mapped[int] = mapped_column(primary_key=True)
    franchise_id: Mapped[int] = mapped_column(
        ForeignKey("franchises.id"),
        index=True,
    )
    day_of_week: Mapped[DayOfWeek] = mapped_column(
        SqlEnum(
            DayOfWeek,
            name="franchise_day_of_week",
            native_enum=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        index=True,
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    open_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    close_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    franchise: Mapped[Franchise] = relationship(back_populates="timings")


class FranchiseReview(Base):
    __tablename__ = "franchise_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    franchise_id: Mapped[int] = mapped_column(
        ForeignKey("franchises.id"),
        index=True,
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id"),
        index=True,
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    rating: Mapped[Decimal] = mapped_column(Numeric(2, 1))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    franchise: Mapped[Franchise] = relationship(back_populates="reviews")
