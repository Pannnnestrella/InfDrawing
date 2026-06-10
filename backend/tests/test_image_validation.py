"""Tests for inpaint image/mask validation."""

import io

import pytest
from fastapi import HTTPException
from PIL import Image

from app.pipeline.image_validation import validate_inpaint_image_mask_pair


def _png_bytes(size: tuple[int, int], color: str) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def test_validate_matching_sizes_passes() -> None:
    validate_inpaint_image_mask_pair(_png_bytes((512, 512), "red"), _png_bytes((512, 512), "white"))


def test_validate_mismatched_sizes_raises() -> None:
    with pytest.raises(HTTPException) as exc_info:
        validate_inpaint_image_mask_pair(
            _png_bytes((512, 512), "red"),
            _png_bytes((256, 256), "white"),
        )
    assert exc_info.value.status_code == 400
    assert "does not match" in exc_info.value.detail
