"""Behavioral tests for finite-support masking and inverse crop mapping."""

import io

import numpy as np
import pytest
from PIL import Image, ImageDraw
from pydantic import ValidationError

from app.controlled_edit.inpaint_crop import inpaint_crop
from app.controlled_edit.inpaint_stitch import inpaint_stitch
from app.controlled_edit.inpaint_types import InpaintOptions, LocalTurnFields
from app.controlled_edit.masks import png_bytes, prepare_mask
from app.controlled_edit.schemas import EditTurnRequest, EditVersion
from app.pipeline.image_providers.inpaint_capabilities import inpaint_capability


@pytest.mark.parametrize(
    "size,box",
    [
        ((101, 79), (0, 0, 20, 20)),
        ((101, 79), (80, 60, 100, 78)),
        ((301, 117), (140, 2, 145, 115)),
        ((4096, 4096), (1500, 1500, 1700, 1700)),
    ],
)
def test_only_mask_support_changes(size: tuple[int, int], box: tuple[int, ...]) -> None:
    source = Image.new("RGBA", size, (11, 31, 71, 123))
    mask = Image.new("L", size)
    ImageDraw.Draw(mask).ellipse(box, fill=255)
    options = InpaintOptions(dilate_px=2, feather_sigma_px=2)
    source_bytes = png_bytes(source)
    crop = inpaint_crop(source_bytes, png_bytes(mask), options)
    result = inpaint_stitch(
        source_bytes, png_bytes(Image.new("RGB", (1008, 1024), "red")), crop.blend, crop.stitcher
    )
    actual = np.asarray(Image.open(io.BytesIO(result)))
    old = np.asarray(source)
    support = np.asarray(Image.open(io.BytesIO(crop.blend))) > 0
    assert actual.shape == old.shape
    assert np.array_equal(actual[~support], old[~support])
    assert np.any(actual[support] != old[support])
    assert set(np.unique(np.asarray(Image.open(io.BytesIO(crop.mask))))) <= {0, 255}


def test_holes_empty_mask_and_union() -> None:
    mask = Image.new("L", (80, 60))
    draw = ImageDraw.Draw(mask)
    draw.rectangle((3, 3, 15, 15), fill=255)
    draw.rectangle((6, 6, 9, 9), fill=0)
    draw.rectangle((70, 50, 75, 55), fill=255)
    options = InpaintOptions(fill_holes=True, dilate_px=0, feather_sigma_px=0)
    prepared = prepare_mask(png_bytes(mask), mask.size, options)
    assert prepared.hard.getpixel((7, 7)) == 255
    assert prepared.bbox == (3, 3, 76, 56)
    with pytest.raises(ValueError, match="empty"):
        prepare_mask(png_bytes(Image.new("L", mask.size)), mask.size, options)


def test_rejects_wrong_source_and_output_ratio() -> None:
    source = png_bytes(Image.new("RGB", (100, 100)))
    mask = png_bytes(Image.new("L", (100, 100), 255))
    crop = inpaint_crop(source, mask, InpaintOptions())
    restored_metadata = type(crop.stitcher).model_validate_json(crop.stitcher.model_dump_json())
    assert restored_metadata == crop.stitcher
    assert inpaint_stitch(source, crop.image, crop.blend, restored_metadata) == inpaint_stitch(
        source, crop.image, crop.blend, crop.stitcher
    )
    with pytest.raises(ValueError, match="hash"):
        inpaint_stitch(
            png_bytes(Image.new("RGB", (100, 100), "red")), source, crop.blend, crop.stitcher
        )
    with pytest.raises(ValueError, match="aspect ratio"):
        inpaint_stitch(source, png_bytes(Image.new("RGB", (100, 200))), crop.blend, crop.stitcher)


def test_capabilities_and_legacy_contracts() -> None:
    wan = inpaint_capability("wanx2.1-imageedit")
    with pytest.raises(ValueError):
        wan.validate_input((511, 1024))
    with pytest.raises(ValueError):
        wan.validate_input((1024, 1024), 10_000_001)
    qwen = inpaint_capability("qwen-image-2.0")
    assert qwen.mask_mode == "unsupported"
    qwen.validate_output((1024, 1536))
    for size in [(1033, 1032), (16, 16), (16, 65536)]:
        with pytest.raises(ValueError):
            qwen.validate_output(size)
    assert EditTurnRequest(parent_version_id="old", instruction="change").edit_mode == "auto"
    assert EditVersion(session_id="old").masks == []
    with pytest.raises(ValidationError):
        LocalTurnFields(edit_mode="local")
