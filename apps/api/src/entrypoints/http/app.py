from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError

from domains.auth.interfaces.http import router as auth_router
from domains.bookings.interfaces.http import (
    booking_items_router,
    router as bookings_router,
)
from domains.catalog.interfaces.http import router as catalog_router
from domains.customers.interfaces.http import customers_router, vehicles_router
from domains.franchises.interfaces.http import router as franchises_router
from domains.invoicing.interfaces.http import router as invoicing_router
from domains.payments.interfaces.http import router as payments_router
# from domains.reports.interfaces.http import router as reports_router
# from domains.settlements.interfaces.http import router as settlements_router
from domains.users.interfaces.http import router as users_router
from foundation.config.settings import get_settings
from foundation.database.bootstrap import create_schema
from foundation.errors import AppError
from foundation.observability import configure_logging
from foundation.web.responses import error_response, validation_error_response

from apps.api.src.entrypoints.http.openapi_docs import (
    API_DESCRIPTION,
    API_VERSION,
    OPENAPI_TAGS,
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    create_schema()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()
    app = FastAPI(
        title=settings.app_name,
        description=API_DESCRIPTION,
        version=API_VERSION,
        # openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
        openapi_url=f"{settings.api_prefix}/openapi.json",
        docs_url=f"{settings.api_prefix}/docs",
        redoc_url=f"{settings.api_prefix}/redoc",
        swagger_ui_parameters={"persistAuthorization": True},
        contact={
            "name": "Backend / API owner",
        },
        license_info={
            "name": "Proprietary — internal integration use",
        },
    )

    @app.exception_handler(RequestValidationError)
    def request_validation_handler(
        _request: Request,
        exc: RequestValidationError,
    ):
        return validation_error_response(exc)

    @app.exception_handler(AppError)
    def app_error_handler(_request: Request, exc: AppError):
        """Same envelope as route-level ``error_response`` for uncaught :class:`AppError`."""
        return error_response(exc)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "app": settings.app_name}

    app.include_router(auth_router, prefix=settings.api_prefix)
    app.include_router(users_router, prefix=settings.api_prefix)
    app.include_router(franchises_router, prefix=settings.api_prefix)
    app.include_router(catalog_router, prefix=settings.api_prefix)
    app.include_router(customers_router, prefix=settings.api_prefix)
    app.include_router(vehicles_router, prefix=settings.api_prefix)
    app.include_router(bookings_router, prefix=settings.api_prefix)
    app.include_router(booking_items_router, prefix=settings.api_prefix)
    app.include_router(invoicing_router, prefix=settings.api_prefix)
    app.include_router(payments_router, prefix=settings.api_prefix)
    # app.include_router(reports_router, prefix=settings.api_prefix)
    # app.include_router(settlements_router, prefix=settings.api_prefix)
    return app
