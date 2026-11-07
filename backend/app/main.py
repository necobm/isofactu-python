"""FastAPI application factory."""

import logging
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

Authentication uses a session cookie obtained from `POST /api/auth/login`. Each `ADMIN`
user is a tenant and only sees its own subjects and invoices; `SUPER_ADMIN` users manage
the accounts under `/api/admin` and have no invoicing data.
"""


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()


def configure_logging(settings: Settings) -> None:
    """Uvicorn only configures its own loggers: give `app.*` a handler and a level so
    that, e.g., e-mails written to the log (no SMTP server) actually show up."""
    logger = logging.getLogger("app")
    logger.setLevel(settings.log_level.upper())
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s: %(message)s"))
        logger.addHandler(handler)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

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
            allow_credentials=True,  # the session cookie
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(api_router)
    mount_spa(app, settings.public_dir)
    return app


app = create_app()
