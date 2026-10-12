"""RGBA pad/restore and alpha reattach helpers for controlled edit."""

from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageDraw

from app.controlled_edit.alpha import (
    flatten_for_model,
    has_meaningful_alpha,
    match_source_size,
    reattach_alpha,
)
from app.controlled_edit.masks import png_bytes
from app.controlled_edit.qwen_mask_prompt import (
    qwen_mask_edit_prompt,
    wants_transparency,
)
from app.controlled_edit.sizing import pad_to_supported, restore_original_frame


def _rgba_disk(size: tuple[int, int] = (64, 48)) -> bytes:
    """Opaque red disk on transparent background."""
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 4, size[0] - 9, size[1] - 5), fill=(200, 40, 40, 255))
    return png_bytes(image)


def test_has_meaningful_alpha_and_flatten() -> None:
    rgba = _rgba_disk()
    assert has_meaningful_alpha(rgba)
    flat = flatten_for_model(rgba, background=(10, 20, 30))
    assert not has_meaningful_alpha(flat)
    with Image.open(io.BytesIO(flat)) as im:
        assert im.mode == "RGB"
        assert im.getpixel((0, 0)) == (10, 20, 30)


def test_pad_restore_preserves_outside_alpha() -> None:
    source = _rgba_disk((90, 50))
    padded = pad_to_supported(source, keep_alpha=True)
    assert padded.mode == "RGBA"
    assert padded.source_had_alpha
    # Simulate opaque model output on the padded canvas, then restore + reattach.
    with Image.open(io.BytesIO(padded.png)) as pad_im:
        fake = Image.new("RGB", pad_im.size, (90, 90, 90))
        fake_bytes = png_bytes(fake)
    restored = restore_original_frame(fake_bytes, padded)
    child = reattach_alpha(source, restored, support_mask=None)
    src = np.asarray(Image.open(io.BytesIO(source)).convert("RGBA"))
    out = np.asarray(Image.open(io.BytesIO(child)).convert("RGBA"))
    assert out.shape == src.shape
    # Fully transparent corners must keep alpha 0.
    assert out[0, 0, 3] == 0
    assert out[0, -1, 3] == 0
    assert np.array_equal(out[..., 3], src[..., 3])


def test_reattach_alpha_outside_support_only() -> None:
    parent = _rgba_disk((80, 60))
    child_rgb = png_bytes(Image.new("RGB", (80, 60), (1, 2, 3)))
    support = Image.new("L", (80, 60), 0)
    ImageDraw.Draw(support).rectangle((20, 15, 50, 40), fill=255)
    support_bytes = png_bytes(support)
    out = reattach_alpha(parent, child_rgb, support_bytes)
    parent_a = np.asarray(Image.open(io.BytesIO(parent)).getchannel("A"))
    out_im = np.asarray(Image.open(io.BytesIO(out)).convert("RGBA"))
    support_arr = np.asarray(support) > 0
    assert np.array_equal(out_im[~support_arr, 3], parent_a[~support_arr])
    assert np.all(out_im[support_arr, :3] == (1, 2, 3))


def test_match_source_size_keeps_alpha() -> None:
    source = _rgba_disk((40, 30))
    big = png_bytes(Image.new("RGBA", (80, 60), (5, 6, 7, 128)))
    matched = match_source_size(big, source)
    with Image.open(io.BytesIO(matched)) as im:
        assert im.size == (40, 30)
        assert im.mode == "RGBA"


def test_wants_transparency_and_qwen_prompt() -> None:
    assert wants_transparency("改成红色", parent_has_alpha=True)
    assert wants_transparency("请抠图去背", parent_has_alpha=False)
    assert not wants_transparency("改成红色", parent_has_alpha=False)
    allow = qwen_mask_edit_prompt("换成剑", allow_alpha=True)
    deny = qwen_mask_edit_prompt("换成剑", allow_alpha=False)
    assert "透明通道" in allow
    assert "不要透明通道" in deny or "不透明" in deny
