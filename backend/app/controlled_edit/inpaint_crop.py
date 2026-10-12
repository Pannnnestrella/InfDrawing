"""Deterministic crop preparation with explicit inverse geometry."""

import hashlib
import io
import math
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageOps

from app.controlled_edit.inpaint_types import InpaintOptions, Stitcher
from app.controlled_edit.masks import png_bytes, prepare_mask
from app.pipeline.image_providers.inpaint_capabilities import inpaint_capability


@dataclass(frozen=True)
class CropResult:
    """Model inputs, source-space blending mask, and inverse mapping."""

    image: bytes
    mask: bytes
    blend: bytes
    stitcher: Stitcher


def inpaint_crop(source: bytes, mask: bytes, options: InpaintOptions) -> CropResult:
    """Expand and resize a masked region, recording every spatial transform."""
    capability = inpaint_capability(options.model)
    if capability.mask_mode != "binary_field":
        raise ValueError("model has no verified binary-mask editing interface")
    with Image.open(io.BytesIO(source)) as decoded:
        image = ImageOps.exif_transpose(decoded)
        image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
    prepared = prepare_mask(mask, image.size, options)
    x0, y0, x1, y1 = prepared.bbox
    width, height = image.size
    extent = math.ceil(
        max(
            (x1 - x0) * options.context_from_mask_extend_factor,
            (y1 - y0) * options.context_from_mask_extend_factor,
            x1 - x0 + 2 * options.min_context_px,
            y1 - y0 + 2 * options.min_context_px,
        )
    )
    # The initial Wanx policy is square, not a claim that its API requires square inputs.
    left = math.floor((x0 + x1 - extent) / 2)
    top = math.floor((y0 + y1 - extent) / 2)
    if extent <= width:
        left = min(max(0, left), width - extent)
    if extent <= height:
        top = min(max(0, top), height - extent)
    right, bottom = left + extent, top + extent
    paste = (max(0, left), max(0, top), min(width, right), min(height, bottom))
    padding = (max(0, -left), max(0, -top), max(0, right - width), max(0, bottom - height))
    # Edge padding adds context without ever making the outside-image area editable.
    array = np.asarray(image.crop(paste))
    padded = np.pad(
        array, ((padding[1], padding[3]), (padding[0], padding[2]), (0, 0)), mode="edge"
    )
    working = Image.fromarray(padded).convert("RGB").resize((1024, 1024), Image.Resampling.LANCZOS)
    hard = prepared.hard.crop((left, top, right, bottom)).resize(
        working.size, Image.Resampling.NEAREST
    )
    image_bytes, mask_bytes = png_bytes(working), png_bytes(hard.convert("RGB"))
    capability.validate_input(working.size, len(image_bytes))
    capability.validate_input(hard.size, len(mask_bytes))
    capability.validate_output(working.size)
    stitcher = Stitcher(
        source_size=image.size,
        source_mode=image.mode,
        crop_rect=(left, top, right, bottom),
        paste_rect=paste,
        mask_bbox=prepared.bbox,
        padding=padding,
        canvas_size=(extent, extent),
        model_size=working.size,
        source_sha256=hashlib.sha256(source).hexdigest(),
        options=options,
    )
    return CropResult(image_bytes, mask_bytes, png_bytes(prepared.blend), stitcher)
