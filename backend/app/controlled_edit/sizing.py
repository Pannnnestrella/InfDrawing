"""Pad images to an OpenAI-supported aspect ratio and restore the original frame."""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image

SUPPORTED_SIZES: tuple[tuple[int, int], ...] = ((1024, 1024), (1536, 1024), (1024, 1536))


@dataclass(frozen=True)
class PaddedImage:
    """An image letterboxed onto a supported canvas.

    Attributes:
        png: The padded image encoded as PNG.
        size: The OpenAI ``size`` parameter, e.g. ``"1536x1024"``.
        content_box: Normalized (left, top, right, bottom) of the original content.
        original_size: Original (width, height) in pixels.
    """

    png: bytes
    size: str
    content_box: tuple[float, float, float, float]
    original_size: tuple[int, int]


def choose_size(width: int, height: int) -> tuple[int, int]:
    """Return the supported size whose aspect ratio is closest to ``width / height``."""
    ratio = width / height
    return min(SUPPORTED_SIZES, key=lambda size: abs(size[0] / size[1] - ratio))


def pad_to_supported(image_bytes: bytes) -> PaddedImage:
    """Letterbox ``image_bytes`` so it matches a supported aspect ratio without distortion."""
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
    canvas = Image.new("RGBA", (canvas_w, canvas_h), _edge_color(image))
    canvas.paste(image, (left, top))
    buffer = io.BytesIO()
    canvas.convert("RGB").save(buffer, format="PNG")
    return PaddedImage(
        png=buffer.getvalue(),
        size=f"{target_w}x{target_h}",
        content_box=(
            left / canvas_w,
            top / canvas_h,
            (left + width) / canvas_w,
            (top + height) / canvas_h,
        ),
        original_size=(width, height),
    )


def restore_original_frame(output_bytes: bytes, padded: PaddedImage) -> bytes:
    """Crop the content region out of a generated image and resize to the original size."""
    with Image.open(io.BytesIO(output_bytes)) as generated:
        image = generated.convert("RGB")
    out_w, out_h = image.size
    left, top, right, bottom = padded.content_box
    box = (
        round(left * out_w),
        round(top * out_h),
        round(right * out_w),
        round(bottom * out_h),
    )
    restored = image.crop(box).resize(padded.original_size, Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    restored.save(buffer, format="PNG")
    return buffer.getvalue()


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
