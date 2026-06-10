"""Helpers for text-region inpaint masks."""

from __future__ import annotations

from PIL import Image, ImageDraw


def bbox_to_inpaint_mask(
    width: int,
    height: int,
    bbox: tuple[int, int, int, int],
    *,
    padding: int = 8,
) -> Image.Image:
    """Build binary mask: white = text region to erase."""
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    x0, y0, x1, y1 = bbox
    draw.rectangle(
        (
            max(0, x0 - padding),
            max(0, y0 - padding),
            min(width, x1 + padding),
            min(height, y1 + padding),
        ),
        fill=255,
    )
    return mask
