"""DashScope cloud decompose via Qwen-Image-Edit (chroma matte + scene fill)."""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageChops, ImageOps

from app.config import Settings, settings
from app.controlled_edit.vision import VisionError, scene_vision_client
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

# Sent by older clients when the user left the decompose box empty.
_LEGACY_UNNAMED_PROMPTS = {
    "clean seamless background, high quality",
    "clean seamless background",
}
MAX_NAMED_TARGETS = 6

NAMED_RECOGNITION_PROMPT = (
    "You select objects to split into separate image layers. "
    "The user names what to extract. Return JSON "
    '{"targets":[{"name":"short English description of one visible object",'
    '"label":"short display name in the user\'s language"}]}. '
    "Include only objects the user explicitly asked to separate. "
    "Each target must be visible. One target per named object. "
    "Do not merge a person with held items unless the user named them as one object. "
    "Order targets from back to front. At most 6 targets. "
    "If the user did not name a separable object, return {\"targets\":[]}."
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


def _open_rgba(image_bytes: bytes) -> Image.Image:
    """Decode bytes with EXIF orientation applied (matches browser display)."""
    with Image.open(io.BytesIO(image_bytes)) as image:
        return ImageOps.exif_transpose(image).convert("RGBA")


def apply_edit_difference_alpha(
    source_bytes: bytes,
    edited_bytes: bytes,
    *,
    threshold: int = 28,
) -> Image.Image:
    """Keep original RGB; transparent where the edit diverged (treated as background)."""
    rgba = _open_rgba(source_bytes)
    source_rgb = rgba.convert("RGB")
    with Image.open(io.BytesIO(edited_bytes)) as edited:
        edited_rgb = (
            ImageOps.exif_transpose(edited)
            .convert("RGB")
            .resize(rgba.size, Image.Resampling.BILINEAR)
        )
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
    rgba = _open_rgba(source_bytes)
    with Image.open(io.BytesIO(chroma_bytes)) as plate:
        plate_rgb = (
            ImageOps.exif_transpose(plate)
            .convert("RGB")
            .resize(rgba.size, Image.Resampling.BILINEAR)
        )
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
        width, height = ImageOps.exif_transpose(image).size
    width = max(512, min(2048, width))
    height = max(512, min(2048, height))
    width = max(512, (width // 16) * 16)
    height = max(512, (height // 16) * 16)
    return f"{width}x{height}"


def _png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def is_named_decompose_prompt(prompt: str) -> bool:
    """Return True when the user named objects to split out.

    A blank prompt and the historical default background sentence stay on the
    two-layer subject/background path.
    """
    text = prompt.strip()
    if not text:
        return False
    return text.lower() not in _LEGACY_UNNAMED_PROMPTS


@dataclass(frozen=True)
class NamedTarget:
    """One object the user asked to peel into its own layer."""

    name: str
    label: str


def _layer_label(raw: str, fallback: str) -> str:
    """Keep a short printable layer name for the canvas."""
    cleaned = "".join(
        char for char in raw.strip() if char.isprintable() and char not in "\\/"
    )
    cleaned = cleaned[:32].strip()
    return cleaned or fallback


def parse_named_targets(payload: dict[str, object]) -> list[NamedTarget]:
    """Read the vision JSON object list, capped at ``MAX_NAMED_TARGETS``."""
    raw = payload.get("targets")
    if not isinstance(raw, list):
        raise ImageProviderError("识别结果缺少物体列表")
    targets: list[NamedTarget] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        label = str(item.get("label", "")).strip()
        if not name:
            continue
        targets.append(
            NamedTarget(name=name[:200], label=_layer_label(label, name[:32]))
        )
        if len(targets) >= MAX_NAMED_TARGETS:
            break
    return targets


def matte_from_plate(
    source_bytes: bytes,
    plate_bytes: bytes,
    *,
    small_subject: bool = False,
) -> Image.Image:
    """Keep original RGB and cut alpha from a chroma plate.

    Args:
        source_bytes: Original image. Its pixels are kept.
        plate_bytes: Edit that paints the unwanted region a flat key color.
        small_subject: Accept a thin object. A sword can be well under 8% of the frame.

    Raises:
        ImageProviderError: When the plate does not yield a usable matte.
    """
    with Image.open(io.BytesIO(plate_bytes)) as plate:
        plate_im = ImageOps.exif_transpose(plate).convert("RGB")
    inferred = infer_corner_chroma(plate_im)
    key = inferred or CHROMA_RGB
    coverage = chroma_coverage(plate_im, chroma=key, tolerance=90)
    if small_subject:
        use_chroma = 0.02 <= coverage < 1.0
    else:
        use_chroma = 0.08 <= coverage <= 0.92
    if use_chroma:
        foreground = apply_chroma_alpha(source_bytes, plate_bytes, chroma=key, tolerance=90)
    else:
        foreground = apply_edit_difference_alpha(source_bytes, plate_bytes)
    _require_usable_alpha(foreground, small_subject=small_subject, chroma_path=use_chroma)
    return foreground


def _require_usable_alpha(
    foreground: Image.Image,
    *,
    small_subject: bool,
    chroma_path: bool,
) -> None:
    """Reject an empty matte, and a difference matte that kept the whole frame."""
    alpha = foreground.split()[-1]
    if alpha.getextrema() == (0, 0):
        raise ImageProviderError("matte produced an empty foreground")
    # The historical subject split only bounds the difference fallback.
    if chroma_path and not small_subject:
        return
    opaque_pixels = alpha.histogram()[255]
    total = float(foreground.size[0] * foreground.size[1])
    opaque = opaque_pixels / total if total else 0.0
    if small_subject:
        if opaque_pixels < 64 or opaque > 0.90:
            raise ImageProviderError(f"matte is not usable (opaque={opaque:.2f})")
        return
    if opaque < 0.08 or opaque > 0.92:
        raise ImageProviderError(f"edit-difference matte is not usable (opaque={opaque:.2f})")


def named_chroma_prompt(name: str) -> str:
    """Instruction that paints everything except one named object magenta."""
    return (
        f"Replace everything except {name} with a flat solid color #FF00FF. "
        f"Keep {name} unchanged. Do not keep any other object, person, or clothing. "
        "Do not cast it onto the magenta field. Do not add objects."
    )


def named_fill_prompt(names: list[str]) -> str:
    """Instruction that erases only the named objects and keeps the rest."""
    listed = "; ".join(names)
    return (
        f"Remove only these objects: {listed}. "
        "Fill those empty regions with a natural continuation of the surrounding scene. "
        "Keep every other object, person, and the rest of the image unchanged. "
        "Do not add new people, characters, or props."
    )


async def recognize_named_targets(image_bytes: bytes, prompt: str) -> list[NamedTarget]:
    """Ask the scene model which named objects in the image should become layers."""
    try:
        payload = await scene_vision_client().complete_json(
            system_prompt=NAMED_RECOGNITION_PROMPT,
            user_text=f"User request:\n{prompt.strip()}",
            images=[image_bytes],
        )
    except VisionError as exc:
        raise ImageProviderError(f"物体识别失败：{exc}") from exc
    targets = parse_named_targets(payload)
    if not targets:
        raise ImageProviderError("没有从提示里识别出要拆开的物体。请写明名称，例如「剑、盾」。")
    return targets


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
        foreground = matte_from_plate(image_bytes, chroma_plate)
        background = await self._fill_background(
            image_bytes,
            prompt=BG_FILL_PROMPT,
            size=size,
            on_progress=on_progress,
        )
        return foreground, background

    async def split_named_layers(
        self,
        image_bytes: bytes,
        prompt: str,
        on_progress: ProgressCallback | None = None,
    ) -> list[tuple[str, bytes]]:
        """Split user-named objects into layers. Background is first.

        Returns:
            ``(label, png_bytes)`` pairs. The background keeps everything that
            was not named. Each later layer is original pixels of one object.
        """
        await emit_progress(on_progress, "recognizing")
        targets = await recognize_named_targets(image_bytes, prompt)
        size = _qwen_size(image_bytes)
        target_size = _open_rgba(image_bytes).size
        layers: list[tuple[str, bytes]] = []
        for item in targets:
            await emit_progress(on_progress, "segmenting")
            plate = await self._qwen.multi_image_edit(
                image_bytes=image_bytes,
                reference_images=[],
                prompt=named_chroma_prompt(item.name),
                size=size,
                on_progress=on_progress,
            )
            try:
                foreground = matte_from_plate(image_bytes, plate, small_subject=True)
            except ImageProviderError as exc:
                raise ImageProviderError(f"无法抠出「{item.label}」：{exc}") from exc
            if foreground.size != target_size:
                foreground = foreground.resize(target_size, Image.Resampling.NEAREST)
            layers.append((item.label, _png_bytes(foreground)))
        background = await self._fill_background(
            image_bytes,
            prompt=named_fill_prompt([item.name for item in targets]),
            size=size,
            on_progress=on_progress,
        )
        return [("background", background), *layers]

    async def _fill_background(
        self,
        image_bytes: bytes,
        *,
        prompt: str,
        size: str,
        on_progress: ProgressCallback | None,
    ) -> bytes:
        """Inpaint removed regions and force the result to the source pixel size."""
        await emit_progress(on_progress, "inpainting")
        background = await self._qwen.multi_image_edit(
            image_bytes=image_bytes,
            reference_images=[],
            prompt=prompt,
            size=size,
            on_progress=on_progress,
        )
        target = _open_rgba(image_bytes).size
        with Image.open(io.BytesIO(background)) as bg_im:
            bg_rgb = (
                ImageOps.exif_transpose(bg_im)
                .convert("RGB")
                .resize(target, Image.Resampling.LANCZOS)
            )
        return _png_bytes(bg_rgb)
