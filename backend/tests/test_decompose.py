"""Tests for decompose helpers."""

import io
import sys
from unittest.mock import patch

from PIL import Image

from app.pipeline.decompose import foreground_to_inpaint_mask, rembg_available


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
