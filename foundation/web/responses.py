from __future__ import annotations

from typing import Any

from fastapi import status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from foundation.errors import AppError


def success_response(
    *,
    message: str,
    data: Any,
    status_code: int = status.HTTP_200_OK,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": True,
            "message": message,
            "data": data,
        },
    )


def error_response(exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.message,
            "error_code": exc.error_code,
            "details": exc.details or {},
        },
    )


def validation_error_response(exc: RequestValidationError) -> JSONResponse:
    """Same envelope as :func:`error_response`, for Pydantic / FastAPI request validation."""
    errors = exc.errors()
    normalized: list[dict[str, Any]] = []
    for err in errors:
        loc = err.get("loc")
        item: dict[str, Any] = {
            "loc": [str(part) for part in loc] if loc is not None else [],
            "msg": err.get("msg", ""),
            "type": err.get("type", ""),
        }
        if "input" in err:
            item["input"] = err["input"]
        normalized.append(item)

    message = (normalized[0]["msg"]
               if len(normalized) == 1 else "Request validation failed.")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "message": message,
            "error_code": "VALIDATION_ERROR",
            "details": {
                "errors": normalized
            },
        },
    )


def internal_error_response() -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "message": "Internal server error.",
            "error_code": "INTERNAL_SERVER_ERROR",
            "details": {},
        },
    )
