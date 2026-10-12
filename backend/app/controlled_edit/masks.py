"""Mask preparation in source pixels, with separate generation and blending masks."""

import io
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageChops, ImageFilter
from scipy.ndimage import binary_fill_holes

from app.controlled_edit.inpaint_types import InpaintOptions


def png_bytes(image: Image.Image) -> bytes:
    """Encode an image losslessly as PNG."""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@dataclass(frozen=True)
class PreparedMask:
    """A hard generation mask and finite-support soft blending weights."""

    hard: Image.Image
    blend: Image.Image
    bbox: tuple[int, int, int, int]


def prepare_mask(data: bytes, size: tuple[int, int], options: InpaintOptions) -> PreparedMask:
    """Validate and process a mask without changing source-image coordinates."""
    with Image.open(io.BytesIO(data)) as source:
        if source.size != size:
            raise ValueError("mask dimensions must match the source image")
        mask = source.convert("L")
    binary = np.asarray(mask) >= options.threshold * 255
    if options.fill_holes:
        binary = binary_fill_holes(binary)
    hard = Image.fromarray(binary.astype(np.uint8) * 255)
    if options.dilate_px:
        hard = hard.filter(ImageFilter.MaxFilter(options.dilate_px * 2 + 1))
    bbox = hard.getbbox()
    if bbox is None:
        raise ValueError("mask is empty after threshold filtering")
    soft = hard.filter(ImageFilter.GaussianBlur(options.feather_sigma_px))
    blend = ImageChops.multiply(soft, hard)
    return PreparedMask(hard, blend, bbox)
