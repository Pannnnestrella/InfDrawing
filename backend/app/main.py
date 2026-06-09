from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api import agent, generate, ws
from app.config import settings
from app.storage.local import ensure_data_dirs

app = FastAPI(title=settings.app_name, debug=settings.debug)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agent.router, prefix="/api/v1")
app.include_router(generate.router, prefix="/api/v1")
app.include_router(ws.router, prefix="/api/v1")


@app.on_event("startup")
def on_startup() -> None:
    ensure_data_dirs()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/files/outputs/{filename}")
def get_output_file(filename: str) -> FileResponse:
    path = settings.outputs_dir / filename
    return FileResponse(path)
