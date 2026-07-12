"""OCR text detection via EasyOCR (CPU)."""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image

if TYPE_CHECKING:
    import easyocr


_reader: easyocr.Reader | None = None
_EASYOCR_AVAILABLE: bool | None = None


def easyocr_available() -> bool:
    """Return True when easyocr is importable."""
    global _EASYOCR_AVAILABLE
    if _EASYOCR_AVAILABLE is not None:
        return _EASYOCR_AVAILABLE
    try:
        import easyocr  # noqa: F401

        _EASYOCR_AVAILABLE = True
    except ImportError:
        _EASYOCR_AVAILABLE = False
    return _EASYOCR_AVAILABLE


def _get_reader() -> easyocr.Reader:
    global _reader
    if _reader is None:
        import easyocr

        _reader = easyocr.Reader(["en", "ch_sim"], gpu=False, verbose=False)
    return _reader


@dataclass(frozen=True)
class TextRegion:
    """Detected text block in image pixel coordinates."""

    text: str
    bbox: tuple[int, int, int, int]
    confidence: float


def detect_text_regions(image_bytes: bytes) -> tuple[list[TextRegion], int, int]:
    """Run OCR and return regions plus image dimensions."""
    with Image.open(io.BytesIO(image_bytes)) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        array = np.array(rgb)

    raw_results = _get_reader().readtext(array)
    regions: list[TextRegion] = []
    for bbox_points, text, confidence in raw_results:
        cleaned = str(text).strip()
        if not cleaned:
            continue
        xs = [int(point[0]) for point in bbox_points]
        ys = [int(point[1]) for point in bbox_points]
        x0 = max(0, min(xs))
        y0 = max(0, min(ys))
        x1 = min(width, max(xs))
        y1 = min(height, max(ys))
        if x1 <= x0 or y1 <= y0:
            continue
        regions.append(
            TextRegion(
                text=cleaned,
                bbox=(x0, y0, x1, y1),
                confidence=float(confidence),
            )
        )
    return regions, width, height
