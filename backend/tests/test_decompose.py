"""Tests for decompose helpers."""

import io
import sys
from unittest.mock import patch

from PIL import Image

from app.pipeline.decompose import foreground_to_inpaint_mask, rembg_available
from app.pipeline.image_providers.dashscope_decompose import instance_mask_to_rgba
from app.pipeline.image_providers.dashscope_wanx import _contains_oss_url


def test_rembg_available_false_when_onnxruntime_missing() -> None:
    real_import = __import__

    def fake_import(name: str, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if name == "onnxruntime":
            raise ImportError("no onnxruntime")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        assert rembg_available() is False


def test_rembg_available_false_on_system_exit() -> None:
    real_import = __import__

    def fake_import(name: str, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if name == "rembg":
            sys.exit(1)
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        assert rembg_available() is False


def test_foreground_to_inpaint_mask_inverts_alpha() -> None:
    image = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
    mask = foreground_to_inpaint_mask(image)
    assert mask.mode == "L"
    center = mask.getpixel((2, 2))
    assert center == 0

    transparent = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    mask_bg = foreground_to_inpaint_mask(transparent)
    assert mask_bg.getpixel((2, 2)) == 255


def test_instance_mask_to_rgba_keeps_nonzero_ids() -> None:
    source = io.BytesIO()
    Image.new("RGB", (4, 4), (10, 20, 30)).save(source, format="PNG")
    mask_buf = io.BytesIO()
    mask = Image.new("RGB", (4, 4), (0, 0, 0))
    mask.putpixel((1, 1), (2, 0, 0))
    mask.save(mask_buf, format="PNG")
    rgba = instance_mask_to_rgba(source.getvalue(), mask_buf.getvalue())
    assert rgba.getpixel((1, 1))[3] == 255
    assert rgba.getpixel((0, 0))[3] == 0


def test_contains_oss_url_walks_nested_payload() -> None:
    assert _contains_oss_url({"input": {"image_url": "oss://dashscope/tmp.png"}}) is True
    assert _contains_oss_url({"input": {"image_url": "https://example.com/a.png"}}) is False


def test_infer_corner_chroma_when_corners_agree() -> None:
    from app.pipeline.image_providers.dashscope_decompose import infer_corner_chroma

    image = Image.new("RGB", (20, 20), (12, 200, 12))
    image.putpixel((10, 10), (255, 0, 0))
    assert infer_corner_chroma(image) == (12, 200, 12)


def test_apply_chroma_alpha_keeps_source_rgb() -> None:
    source = io.BytesIO()
    Image.new("RGB", (4, 4), (10, 20, 30)).save(source, format="PNG")
    plate = Image.new("RGB", (4, 4), (255, 0, 255))
    plate.putpixel((1, 1), (10, 20, 30))
    plate_buf = io.BytesIO()
    plate.save(plate_buf, format="PNG")
    from app.pipeline.image_providers.dashscope_decompose import apply_chroma_alpha

    rgba = apply_chroma_alpha(source.getvalue(), plate_buf.getvalue())
    assert rgba.getpixel((1, 1)) == (10, 20, 30, 255)
    assert rgba.getpixel((0, 0))[3] == 0
