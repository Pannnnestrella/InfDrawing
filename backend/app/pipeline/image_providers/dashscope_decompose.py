"""DashScope cloud decompose via Qwen-Image-Edit (chroma matte + scene fill)."""

from __future__ import annotations

import io

from PIL import Image, ImageChops

from app.config import Settings, settings
from app.pipeline.image_providers.base import (
    ImageProviderError,
    ProgressCallback,
    emit_progress,
)
from app.pipeline.image_providers.dashscope_qwen_edit import DashScopeQwenEditProvider

# Magenta is rare in illustration palettes and keys cleanly.
CHROMA_RGB = (255, 0, 255)
CHROMA_TOLERANCE = 70

FG_CHROMA_PROMPT = (
    "Replace ONLY the background with a flat solid color #FF00FF. "
    "Keep the main subject, clothing, and held objects unchanged. "
    "Do not cast the subject onto the magenta field. Do not add objects."
)
BG_FILL_PROMPT = (
    "Remove the main subject and every foreground object. "
    "Fill the empty region with a natural continuation of the environment. "
    "Do not add people, characters, or props."
)


def dashscope_decompose_available(config: Settings = settings) -> bool:
    """Return True when the Aliyun key can run cloud decompose."""
    return bool(config.dashscope_api_key.strip())


def instance_mask_to_rgba(source_bytes: bytes, mask_bytes: bytes) -> Image.Image:
    """Paint source RGB with alpha from a non-zero instance-id mask."""
    with Image.open(io.BytesIO(source_bytes)) as source:
        rgba = source.convert("RGBA")
    with Image.open(io.BytesIO(mask_bytes)) as mask_im:
        mask_rgb = mask_im.convert("RGB").resize(rgba.size, Image.Resampling.NEAREST)
    alpha = mask_rgb.split()[0].point(lambda pixel: 255 if pixel > 0 else 0)
    rgba.putalpha(alpha)
    return rgba


def chroma_coverage(edited: Image.Image, *, chroma: tuple[int, int, int] = CHROMA_RGB, tolerance: int = CHROMA_TOLERANCE) -> float:
    """Return the fraction of pixels within ``tolerance`` of ``chroma``."""
    rgb = edited.convert("RGB")
    key = Image.new("RGB", rgb.size, chroma)
    diff = ImageChops.difference(rgb, key)
    # Max-channel distance; flatten to a 0/255 mask.
    bands = diff.split()
    dist = ImageChops.lighter(ImageChops.lighter(bands[0], bands[1]), bands[2])
    binary = dist.point(lambda value: 255 if value <= tolerance else 0)
    extrema = binary.getextrema()
    if extrema == (0, 0):
        return 0.0
    histogram = binary.histogram()
    chroma_pixels = histogram[255] if len(histogram) > 255 else 0
    return chroma_pixels / float(rgb.size[0] * rgb.size[1])


def infer_corner_chroma(image: Image.Image, *, inset: int = 8, max_spread: int = 45) -> tuple[int, int, int] | None:
    """Return a solid key color if the four corners agree."""
    rgb = image.convert("RGB")
    width, height = rgb.size
    inset_x = min(inset, max(0, width // 8))
    inset_y = min(inset, max(0, height // 8))
    samples = [
        rgb.getpixel((inset_x, inset_y)),
        rgb.getpixel((width - 1 - inset_x, inset_y)),
        rgb.getpixel((inset_x, height - 1 - inset_y)),
        rgb.getpixel((width - 1 - inset_x, height - 1 - inset_y)),
    ]
    means = tuple(sum(channel) // 4 for channel in zip(*samples))
    for sample in samples:
        if max(abs(sample[i] - means[i]) for i in range(3)) > max_spread:
            return None
    return (int(means[0]), int(means[1]), int(means[2]))


def apply_edit_difference_alpha(
    source_bytes: bytes,
    edited_bytes: bytes,
    *,
    threshold: int = 28,
) -> Image.Image:
    """Keep original RGB; transparent where the edit diverged (treated as background)."""
    with Image.open(io.BytesIO(source_bytes)) as source:
        rgba = source.convert("RGBA")
        source_rgb = source.convert("RGB")
    with Image.open(io.BytesIO(edited_bytes)) as edited:
        edited_rgb = edited.convert("RGB").resize(rgba.size, Image.Resampling.BILINEAR)
    diff = ImageChops.difference(source_rgb, edited_rgb)
    bands = diff.split()
    dist = ImageChops.lighter(ImageChops.lighter(bands[0], bands[1]), bands[2])
    alpha = dist.point(lambda value: 0 if value >= threshold else 255)
    rgba.putalpha(alpha)
    return rgba


def apply_chroma_alpha(
    source_bytes: bytes,
    chroma_bytes: bytes,
    *,
    chroma: tuple[int, int, int] = CHROMA_RGB,
    tolerance: int = CHROMA_TOLERANCE,
) -> Image.Image:
    """Keep original RGB; set alpha from a chroma-key plate."""
    with Image.open(io.BytesIO(source_bytes)) as source:
        rgba = source.convert("RGBA")
    with Image.open(io.BytesIO(chroma_bytes)) as plate:
        plate_rgb = plate.convert("RGB").resize(rgba.size, Image.Resampling.BILINEAR)
    key = Image.new("RGB", rgba.size, chroma)
    diff = ImageChops.difference(plate_rgb, key)
    bands = diff.split()
    dist = ImageChops.lighter(ImageChops.lighter(bands[0], bands[1]), bands[2])
    alpha = dist.point(lambda value: 0 if value <= tolerance else 255)
    rgba.putalpha(alpha)
    return rgba


def _qwen_size(image_bytes: bytes) -> str:
    """Pick a DashScope size near the source, clamped to 512–2048 and multiples of 16."""
    with Image.open(io.BytesIO(image_bytes)) as image:
        width, height = image.size
    width = max(512, min(2048, width))
    height = max(512, min(2048, height))
    width = max(512, (width // 16) * 16)
    height = max(512, (height // 16) * 16)
    return f"{width}x{height}"


def _png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class DashScopeDecomposeClient:
    """Split layers with Qwen-Image-Edit (working DashScope multimodal API)."""

    def __init__(self, config: Settings = settings) -> None:
        self._qwen = DashScopeQwenEditProvider(config)

    async def split_layers(
        self,
        image_bytes: bytes,
        on_progress: ProgressCallback | None = None,
    ) -> tuple[Image.Image, bytes]:
        """Return (foreground RGBA from original pixels, background PNG bytes)."""
        size = _qwen_size(image_bytes)
        await emit_progress(on_progress, "segmenting")
        chroma_plate = await self._qwen.multi_image_edit(
            image_bytes=image_bytes,
            reference_images=[],
            prompt=FG_CHROMA_PROMPT,
            size=size,
            on_progress=on_progress,
        )
        with Image.open(io.BytesIO(chroma_plate)) as plate:
            plate_im = plate.convert("RGB")
            inferred = infer_corner_chroma(plate_im)
            key = inferred or CHROMA_RGB
            coverage = chroma_coverage(plate_im, chroma=key, tolerance=90)
        if 0.08 <= coverage <= 0.92:
            foreground = apply_chroma_alpha(
                image_bytes, chroma_plate, chroma=key, tolerance=90
            )
        else:
            foreground = apply_edit_difference_alpha(image_bytes, chroma_plate)
            alpha = foreground.split()[-1]
            total = float(foreground.size[0] * foreground.size[1])
            opaque = alpha.histogram()[255] / total
            if opaque < 0.08 or opaque > 0.92:
                raise ImageProviderError(
                    f"edit-difference matte is not usable (opaque={opaque:.2f})"
                )
        if foreground.split()[-1].getextrema() == (0, 0):
            raise ImageProviderError("matte produced an empty foreground")

        await emit_progress(on_progress, "inpainting")
        background = await self._qwen.multi_image_edit(
            image_bytes=image_bytes,
            reference_images=[],
            prompt=BG_FILL_PROMPT,
            size=size,
            on_progress=on_progress,
        )
        with Image.open(io.BytesIO(image_bytes)) as source:
            target = source.size
        with Image.open(io.BytesIO(background)) as bg_im:
            bg_rgb = bg_im.convert("RGB").resize(target, Image.Resampling.LANCZOS)
        return foreground, _png_bytes(bg_rgb)
