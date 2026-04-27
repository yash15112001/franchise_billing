from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SqlEnum, ForeignKey, Index, JSON, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from domains.users.domain.access import UserRole
from foundation.database.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index(
            "uq_user_franchise_username_not_deleted",
            "franchise_id",
            "username",
            unique=True,
            postgresql_where=text("is_deleted IS FALSE"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(
        SqlEnum(
            UserRole,
            name="user_role",
            native_enum=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        index=True,
    )
    franchise_id: Mapped[int | None] = mapped_column(
        ForeignKey("franchises.id"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    extra_permissions: Mapped[list[str]] = mapped_column(JSON, default=list)
    revoked_permissions: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
