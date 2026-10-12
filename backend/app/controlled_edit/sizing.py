"""Pad images to an OpenAI-supported aspect ratio and restore the original frame."""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Literal

from PIL import Image

from app.controlled_edit.alpha import has_meaningful_alpha
from app.controlled_edit.masks import png_bytes

SUPPORTED_SIZES: tuple[tuple[int, int], ...] = ((1024, 1024), (1536, 1024), (1024, 1536))


@dataclass(frozen=True)
class PaddedImage:
    """An image letterboxed onto a supported canvas.

    Attributes:
        png: The padded image encoded as PNG.
        size: The OpenAI ``size`` parameter, e.g. ``"1536x1024"``.
        content_box: Normalized (left, top, right, bottom) of the original content.
        original_size: Original (width, height) in pixels.
        mode: Channel mode of ``png`` (RGB or RGBA).
        source_had_alpha: Whether the source had a meaningful alpha channel.
    """

    png: bytes
    size: str
    content_box: tuple[float, float, float, float]
    original_size: tuple[int, int]
    mode: Literal["RGB", "RGBA"] = "RGB"
    source_had_alpha: bool = False


def choose_size(width: int, height: int) -> tuple[int, int]:
    """Return the supported size whose aspect ratio is closest to ``width / height``."""
    ratio = width / height
    return min(SUPPORTED_SIZES, key=lambda size: abs(size[0] / size[1] - ratio))


def pad_to_supported(
    image_bytes: bytes,
    *,
    keep_alpha: bool | None = None,
) -> PaddedImage:
    """Letterbox ``image_bytes`` so it matches a supported aspect ratio without distortion.

    When ``keep_alpha`` is None, alpha is kept iff the source has meaningful transparency.
    """
    source_had_alpha = has_meaningful_alpha(image_bytes)
    retain = source_had_alpha if keep_alpha is None else keep_alpha
    with Image.open(io.BytesIO(image_bytes)) as source:
        image = source.convert("RGBA")
    width, height = image.size
    target_w, target_h = choose_size(width, height)
    target_ratio = target_w / target_h
    if width / height > target_ratio:
        canvas_w, canvas_h = width, round(width / target_ratio)
    else:
        canvas_w, canvas_h = round(height * target_ratio), height
    left, top = (canvas_w - width) // 2, (canvas_h - height) // 2
    if retain:
        canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        canvas.paste(image, (left, top), image)
        mode: Literal["RGB", "RGBA"] = "RGBA"
        encoded = png_bytes(canvas)
    else:
        canvas = Image.new("RGBA", (canvas_w, canvas_h), _edge_color(image))
        canvas.paste(image, (left, top))
        mode = "RGB"
        encoded = png_bytes(canvas.convert("RGB"))
    return PaddedImage(
        png=encoded,
        size=f"{target_w}x{target_h}",
        content_box=(
            left / canvas_w,
            top / canvas_h,
            (left + width) / canvas_w,
            (top + height) / canvas_h,
        ),
        original_size=(width, height),
        mode=mode,
        source_had_alpha=source_had_alpha,
    )


def restore_original_frame(output_bytes: bytes, padded: PaddedImage) -> bytes:
    """Crop the content region out of a generated image and resize to the original size."""
    with Image.open(io.BytesIO(output_bytes)) as generated:
        keep_a = padded.source_had_alpha or padded.mode == "RGBA" or "A" in generated.getbands()
        image = generated.convert("RGBA" if keep_a else "RGB")
    out_w, out_h = image.size
    left, top, right, bottom = padded.content_box
    box = (
        round(left * out_w),
        round(top * out_h),
        round(right * out_w),
        round(bottom * out_h),
    )
    restored = image.crop(box).resize(padded.original_size, Image.Resampling.LANCZOS)
    if keep_a and restored.mode == "RGBA" and not has_meaningful_alpha(png_bytes(restored)):
        # Model returned opaque RGB-like data; still emit RGBA so callers can reattach.
        pass
    return png_bytes(restored)


def _edge_color(image: Image.Image) -> tuple[int, int, int, int]:
    """Average border color, so padding blends in instead of adding a hard frame."""
    width, height = image.size
    pixels = [
        image.getpixel((x, y))
        for x, y in (
            (0, 0),
            (width - 1, 0),
            (0, height - 1),
            (width - 1, height - 1),
            (width // 2, 0),
            (width // 2, height - 1),
            (0, height // 2),
            (width - 1, height // 2),
        )
    ]
    channels = list(zip(*pixels, strict=True))
    r, g, b = (sum(c) // len(c) for c in channels[:3])
    return (r, g, b, 255)
