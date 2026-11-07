"""Top-level API router: everything is exposed under the `/api` prefix."""

from fastapi import APIRouter

from app.accounts.router import admin_router, auth_router
from app.core.config import Settings, get_settings
from app.invoicing.router import (
    fiscal_data_router,
    invoice_router,
    serial_router,
    subject_router,
)
from app.invoicing.schemas import HealthStatus

api_router = APIRouter(prefix="/api")


@api_router.get("/health", response_model=HealthStatus, tags=["System"], summary="Health check")
async def health() -> HealthStatus:
    settings: Settings = get_settings()
    return HealthStatus(status="ok", app=settings.app_name, version=settings.app_version)


api_router.include_router(auth_router)
api_router.include_router(admin_router)
api_router.include_router(fiscal_data_router)
api_router.include_router(serial_router)
api_router.include_router(invoice_router)
api_router.include_router(subject_router)
