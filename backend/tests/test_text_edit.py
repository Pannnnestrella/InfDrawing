"""Tests for text edit helpers."""

from app.pipeline.text_edit import bbox_to_inpaint_mask


def test_bbox_to_inpaint_mask_marks_region_white() -> None:
    mask = bbox_to_inpaint_mask(100, 80, (10, 20, 40, 50), padding=0)
    assert mask.size == (100, 80)
    assert mask.getpixel((25, 35)) == 255
    assert mask.getpixel((0, 0)) == 0
