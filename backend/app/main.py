"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.core.config import Settings, get_settings
from app.core.database import dispose_engine
from app.spa import mount_spa

DESCRIPTION = """
Invoice management API for freelancers and SMEs with a Spanish tax context
(VAT, retention, NIF/CIF identification).

* **Subjects** — companies or persons identified by NIF/CIF acting as issuer or recipient.
* **Invoices** — link an issuer and a recipient, have a date and a number and contain lines.

Monetary amounts are JSON numbers with at most two decimals (`120.98`).
"""


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=DESCRIPTION,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
        debug=settings.debug,
    )

    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(api_router)
    mount_spa(app, settings.public_dir)
    return app


app = create_app()
