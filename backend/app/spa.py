"""Serve the built frontend (Vite output in the `public` directory) as a single-page app."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles


class SPAStaticFiles(StaticFiles):
    """Static files with history-API fallback: unknown paths return `index.html`."""

    async def get_response(self, path: str, scope):  # type: ignore[override]
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404 and not path.startswith("api/"):
                return await super().get_response("index.html", scope)
            raise


def mount_spa(app: FastAPI, public_dir: Path) -> None:
    if (public_dir / "index.html").is_file():
        app.mount("/", SPAStaticFiles(directory=public_dir, html=True), name="spa")
        return

    @app.get("/", include_in_schema=False)
    async def frontend_not_built() -> JSONResponse:
        return JSONResponse(
            {
                "detail": "Frontend assets not found. Build them with "
                "`cd frontend && npm run build` (output goes to ./public) "
                "or run `docker compose up`.",
                "public_dir": str(public_dir),
                "docs": "/api/docs",
            },
            status_code=503,
        )
