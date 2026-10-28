"""Top-level API router: everything is exposed under the `/api` prefix."""

from fastapi import APIRouter

from app.core.config import Settings, get_settings
from app.invoicing.router import invoice_router, subject_router
from app.invoicing.schemas import HealthStatus

api_router = APIRouter(prefix="/api")


@api_router.get("/health", response_model=HealthStatus, tags=["System"], summary="Health check")
async def health() -> HealthStatus:
    settings: Settings = get_settings()
    return HealthStatus(status="ok", app=settings.app_name, version=settings.app_version)


api_router.include_router(invoice_router)
api_router.include_router(subject_router)
