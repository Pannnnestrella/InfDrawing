"""Alpha-channel helpers for controlled-edit PNG pipelines."""

from __future__ import annotations

import io

import numpy as np
from PIL import Image

from app.controlled_edit.masks import png_bytes


def has_meaningful_alpha(image_bytes: bytes, *, threshold: int = 250) -> bool:
    """Return True when any pixel is meaningfully below opaque."""
    with Image.open(io.BytesIO(image_bytes)) as source:
        if "A" not in source.getbands():
            return False
        alpha = np.asarray(source.getchannel("A"))
    return bool(np.any(alpha < threshold))


def flatten_for_model(
    image_bytes: bytes,
    *,
    background: tuple[int, int, int] = (127, 127, 127),
) -> bytes:
    """Composite RGBA onto an opaque background for models that reject alpha."""
    with Image.open(io.BytesIO(image_bytes)) as source:
        rgba = source.convert("RGBA")
        canvas = Image.new("RGB", rgba.size, background)
        canvas.paste(rgba, mask=rgba.getchannel("A"))
        return png_bytes(canvas)


def reattach_alpha(
    parent_bytes: bytes,
    child_bytes: bytes,
    support_mask: bytes | None = None,
) -> bytes:
    """Restore parent alpha outside an optional edit support; keep child RGB.

    When ``support_mask`` is None, copy parent alpha everywhere the child has no
    alpha channel. When the child already has alpha, prefer child alpha inside
    support (or everywhere if support is None) and parent alpha outside support.
    """
    with Image.open(io.BytesIO(parent_bytes)) as parent_im:
        parent = parent_im.convert("RGBA")
    with Image.open(io.BytesIO(child_bytes)) as child_im:
        if child_im.size != parent.size:
            child_im = child_im.resize(parent.size, Image.Resampling.LANCZOS)
        child_has_a = "A" in child_im.getbands()
        child = child_im.convert("RGBA")
    if not has_meaningful_alpha(parent_bytes) and not child_has_a:
        return png_bytes(child.convert("RGB"))
    parent_a = np.asarray(parent.getchannel("A"), dtype=np.uint8)
    child_rgb = np.asarray(child)[..., :3]
    if child_has_a and has_meaningful_alpha(child_bytes):
        child_a = np.asarray(child.getchannel("A"), dtype=np.uint8)
    else:
        child_a = parent_a
    if support_mask is not None:
        with Image.open(io.BytesIO(support_mask)) as mask_im:
            if mask_im.size != parent.size:
                mask_im = mask_im.resize(parent.size, Image.Resampling.NEAREST)
            support = np.asarray(mask_im.convert("L")) > 0
        out_a = np.where(support, child_a, parent_a)
    else:
        out_a = child_a if child_has_a and has_meaningful_alpha(child_bytes) else parent_a
    out = np.dstack((child_rgb, out_a))
    return png_bytes(Image.fromarray(out, mode="RGBA"))


def match_source_size(output_bytes: bytes, source_bytes: bytes) -> bytes:
    """Resize model output to the parent frame, preserving alpha when present."""
    with Image.open(io.BytesIO(source_bytes)) as source:
        target = source.size
        want_rgba = "A" in source.getbands() or has_meaningful_alpha(output_bytes)
    with Image.open(io.BytesIO(output_bytes)) as image:
        mode = "RGBA" if want_rgba or "A" in image.getbands() else "RGB"
        converted = image.convert(mode)
        if converted.size == target:
            return png_bytes(converted)
        resized = converted.resize(target, Image.Resampling.LANCZOS)
        return png_bytes(resized)
