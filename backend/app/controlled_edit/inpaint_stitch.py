"""Inverse crop mapping and finite-mask blending, without model inference."""

import hashlib
import io

import numpy as np
from PIL import Image, ImageOps

from app.controlled_edit.inpaint_types import Stitcher
from app.controlled_edit.masks import png_bytes


def inpaint_stitch(source: bytes, generated: bytes, blend: bytes, stitcher: Stitcher) -> bytes:
    """Blend a restored crop while preserving every source pixel outside mask support."""
    if hashlib.sha256(source).hexdigest() != stitcher.source_sha256:
        raise ValueError("stitch source does not match the recorded image hash")
    with Image.open(io.BytesIO(source)) as decoded:
        original = ImageOps.exif_transpose(decoded).convert(stitcher.source_mode)
    with Image.open(io.BytesIO(generated)) as decoded:
        actual = decoded.size
        expected_ratio = stitcher.model_size[0] / stitcher.model_size[1]
        if abs(actual[0] / actual[1] / expected_ratio - 1) > 0.03:
            raise ValueError("generated crop aspect ratio differs from the working canvas")
        restored = decoded.convert(stitcher.source_mode).resize(
            stitcher.canvas_size, Image.Resampling.LANCZOS
        )
    with Image.open(io.BytesIO(blend)) as decoded:
        if decoded.size != original.size:
            raise ValueError("blend mask dimensions differ from source")
        weights = np.asarray(decoded.convert("L"), dtype=np.float32) / 255
    x0, y0, x1, y1 = stitcher.paste_rect
    left, top, _, _ = stitcher.padding
    patch = np.asarray(restored.crop((left, top, left + x1 - x0, top + y1 - y0)), dtype=np.float32)
    result = np.array(original)
    before = result[y0:y1, x0:x1].astype(np.float32)
    alpha = weights[y0:y1, x0:x1, None]
    if stitcher.source_mode == "RGBA":
        old_a, new_a = before[..., 3:4] / 255, patch[..., 3:4] / 255
        out_a = old_a * (1 - alpha) + new_a * alpha
        premult = before[..., :3] * old_a * (1 - alpha) + patch[..., :3] * new_a * alpha
        rgb = np.divide(premult, out_a, out=np.zeros_like(premult), where=out_a > 0)
        mixed = np.concatenate((rgb, out_a * 255), axis=-1)
    else:
        mixed = patch * alpha + before * (1 - alpha)
    changed = alpha[..., 0] > 0
    region = result[y0:y1, x0:x1]
    region[changed] = np.clip(np.rint(mixed[changed]), 0, 255).astype(np.uint8)
    return png_bytes(Image.fromarray(result))
