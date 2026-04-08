from __future__ import annotations

from dataclasses import dataclass

from domains.users.domain.access import MAIN_ADMIN_ROLE, UserRole
from domains.users.infrastructure.models import User


@dataclass
class UserContext:
    user: User
    active_franchise_id: int | None
    permissions: set[str]
    role: UserRole

    @property
    def is_main_admin(self) -> bool:
        return self.role.value == MAIN_ADMIN_ROLE

    @property
    def franchise_id(self) -> int | None:
        return self.active_franchise_id or self.user.franchise_id


@dataclass
class FranchiseScope:
    franchise_id: int
