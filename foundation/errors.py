from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AppError(Exception):
    status_code: int
    message: str
    error_code: str
    details: dict | None = None

    def __post_init__(self) -> None:
        super().__init__(self.message)
        if self.details is None:
            self.details = {}
