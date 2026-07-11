"""Small shared PIL helpers for pipeline executors."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image


def image_to_png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def ensure_rgba_on_disk(src: Path, dest: Path) -> None:
    with Image.open(src) as image:
        image.convert("RGBA").save(dest, format="PNG")
