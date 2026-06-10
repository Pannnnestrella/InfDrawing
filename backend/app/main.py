from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api import agent, generate, system, vision, ws
from app.config import settings
from app.storage.local import ensure_data_dirs

app = FastAPI(title=settings.app_name, debug=settings.debug)

LOCAL_DEV_ORIGIN = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=LOCAL_DEV_ORIGIN,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Type", "Content-Length"],
)

app.include_router(agent.router, prefix="/api/v1")
app.include_router(generate.router, prefix="/api/v1")
app.include_router(system.router, prefix="/api/v1")
app.include_router(vision.router, prefix="/api/v1")
app.include_router(ws.router, prefix="/api/v1")


@app.on_event("startup")
def on_startup() -> None:
    ensure_data_dirs()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/files/outputs/{filename}")
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
        or origin.startswith("http://localhost:")
        or origin.startswith("http://127.0.0.1:")
    ):
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"

    return FileResponse(path, media_type="image/png", headers=headers)
