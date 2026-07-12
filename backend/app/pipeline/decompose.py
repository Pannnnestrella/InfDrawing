"""Image layer extraction helpers for decompose pipeline."""

from __future__ import annotations

import io

from PIL import Image, ImageOps

_REMBG_AVAILABLE: bool | None = None


def rembg_available() -> bool:
    """Return True when rembg and its onnxruntime backend are importable."""
    global _REMBG_AVAILABLE
    if _REMBG_AVAILABLE is not None:
        return _REMBG_AVAILABLE
    try:
        import onnxruntime  # noqa: F401
        import rembg  # noqa: F401

        _REMBG_AVAILABLE = True
    except ImportError:
        _REMBG_AVAILABLE = False
    except SystemExit:
        # rembg calls sys.exit(1) when onnxruntime is missing at import time
        _REMBG_AVAILABLE = False
    return _REMBG_AVAILABLE


def extract_foreground_rgba(image_bytes: bytes) -> Image.Image:
    """Remove background via rembg and return RGBA image."""
    from rembg import remove

    with Image.open(io.BytesIO(image_bytes)) as source:
        rgb = source.convert("RGB")
    result = remove(rgb)
    if isinstance(result, bytes):
        return Image.open(io.BytesIO(result)).convert("RGBA")
    return result.convert("RGBA")


def foreground_to_inpaint_mask(foreground_rgba: Image.Image) -> Image.Image:
    """Build binary mask: white = foreground region to inpaint away."""
    alpha = foreground_rgba.split()[-1]
    return ImageOps.invert(alpha.point(lambda value: 255 if value > 16 else 0))
