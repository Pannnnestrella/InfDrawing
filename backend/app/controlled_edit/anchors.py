"""Reference crops ("anchors") for locked entities."""

from __future__ import annotations

import io

from PIL import Image

from app.controlled_edit.schemas import BBox

ANCHOR_PADDING = 0.15
ANCHOR_MIN_SIDE = 256


def padded_pixel_rect(
    size: tuple[int, int],
    bbox: BBox,
    padding: float = ANCHOR_PADDING,
) -> tuple[int, int, int, int]:
    """Return the inclusive-exclusive pixel box of ``bbox`` plus relative padding."""
    width, height = size
    pad_x, pad_y = bbox.w * padding, bbox.h * padding
    left = max(0, int((bbox.x - pad_x) * width))
    top = max(0, int((bbox.y - pad_y) * height))
    right = min(width, max(left + 1, round((bbox.x + bbox.w + pad_x) * width)))
    bottom = min(height, max(top + 1, round((bbox.y + bbox.h + pad_y) * height)))
    return left, top, right, bottom


def crop_entity(image_bytes: bytes, bbox: BBox, padding: float = ANCHOR_PADDING) -> bytes:
    """Crop ``bbox`` (plus relative padding) from an image and return PNG bytes.

    Small crops are upscaled so the shorter side is at least ``ANCHOR_MIN_SIDE`` pixels,
    which keeps facial detail legible for the image model.
    """
    with Image.open(io.BytesIO(image_bytes)) as source:
        image = source.convert("RGB")
    left, top, right, bottom = padded_pixel_rect(image.size, bbox, padding)
    crop = image.crop((left, top, right, bottom))
    short_side = min(crop.size)
    if short_side < ANCHOR_MIN_SIDE:
        scale = ANCHOR_MIN_SIDE / short_side
        crop = crop.resize(
            (round(crop.width * scale), round(crop.height * scale)),
            Image.Resampling.LANCZOS,
        )
    buffer = io.BytesIO()
    crop.save(buffer, format="PNG")
    return buffer.getvalue()
