"""Validate uploaded image and mask dimensions for inpaint."""

import io

from fastapi import HTTPException
from PIL import Image


def validate_inpaint_image_mask_pair(image_bytes: bytes, mask_bytes: bytes) -> None:
    """Ensure image and mask share the same pixel dimensions.

    Args:
        image_bytes: Raw bytes of the source image.
        mask_bytes: Raw bytes of the mask image.

    Raises:
        HTTPException: If either file is invalid or sizes differ.
    """
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            image_size = image.size
        with Image.open(io.BytesIO(mask_bytes)) as mask:
            mask_size = mask.size
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid image file: {exc}") from exc

    if image_size != mask_size:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Mask size {mask_size[0]}x{mask_size[1]} does not match "
                f"image size {image_size[0]}x{image_size[1]}"
            ),
        )
