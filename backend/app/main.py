from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response

from app.api import agent, artifacts, generate, jobs, system, vision, ws
from app.assets import api as assets_api
from app.config import settings
from app.controlled_edit import api as controlled_edit_api
from app.production.auth import require_scopes
from app.production.http import (
    RedisRateLimitMiddleware,
    RequestIdMiddleware,
    install_error_handlers,
    install_log_redaction,
)
from app.production.infrastructure import check_production_dependencies
from app.production.metrics import MetricsMiddleware, metrics_response
from app.storage.local import ensure_data_dirs


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Validate configuration and initialize local runtime directories."""
    settings.validate_runtime()
    install_log_redaction()
    ensure_data_dirs()
    await check_production_dependencies()
    yield


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)

LOCAL_DEV_ORIGIN = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=LOCAL_DEV_ORIGIN if settings.environment != "production" else None,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "Idempotency-Key", "X-Request-ID"],
    expose_headers=["Content-Type", "Content-Length"],
)
app.add_middleware(RedisRateLimitMiddleware)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(MetricsMiddleware)
install_error_handlers(app)

app.include_router(
    agent.router,
    prefix="/api/v1",
    dependencies=[Depends(require_scopes("agent:plan"))],
)
app.include_router(
    generate.router,
    prefix="/api/v1",
    dependencies=[Depends(require_scopes("generate"))],
)
app.include_router(artifacts.router, prefix="/api/v1")
app.include_router(jobs.router, prefix="/api/v1")
app.include_router(system.router, prefix="/api/v1")
app.include_router(
    vision.router,
    prefix="/api/v1",
    dependencies=[Depends(require_scopes("vision"))],
)
app.include_router(ws.router, prefix="/api/v1")
app.include_router(
    controlled_edit_api.router,
    prefix="/api/v1",
    dependencies=[Depends(require_scopes("controlled_edit"))],
)
app.include_router(
    assets_api.router,
    prefix="/api/v1",
    dependencies=[Depends(require_scopes("assets"))],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
async def readiness() -> dict[str, str]:
    """Report whether configured production dependencies are reachable."""
    try:
        await check_production_dependencies()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="dependencies unavailable") from exc
    return {"status": "ready"}


@app.get("/metrics")
def metrics() -> Response:
    """Expose Prometheus metrics."""
    return metrics_response()


@app.get(
    "/api/v1/files/outputs/{filename}",
    dependencies=[Depends(require_scopes("artifacts:read"))],
)
def get_output_file(filename: str, request: Request) -> FileResponse:
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="invalid filename")
    path = settings.outputs_dir / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="file not found")

    headers: dict[str, str] = {"Cache-Control": "no-cache"}
    origin = request.headers.get("origin")
    if origin and (
        origin in settings.cors_origins
        or (
            settings.environment != "production"
            and (
                origin.startswith("http://localhost:")
                or origin.startswith("http://127.0.0.1:")
            )
        )
    ):
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"

    return FileResponse(path, media_type="image/png", headers=headers)
