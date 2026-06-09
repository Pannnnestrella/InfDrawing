import shutil
import uuid
from pathlib import Path

from app.config import settings


def ensure_data_dirs() -> None:
    for path in (settings.uploads_dir, settings.outputs_dir, settings.logs_dir):
        path.mkdir(parents=True, exist_ok=True)


def save_upload(filename: str, data: bytes) -> Path:
    ensure_data_dirs()
    suffix = Path(filename).suffix or ".png"
    dest = settings.uploads_dir / f"{uuid.uuid4().hex}{suffix}"
    dest.write_bytes(data)
    return dest


def save_upload_copy(source: Path) -> Path:
    ensure_data_dirs()
    dest = settings.uploads_dir / f"{uuid.uuid4().hex}{source.suffix}"
    shutil.copy2(source, dest)
    return dest
