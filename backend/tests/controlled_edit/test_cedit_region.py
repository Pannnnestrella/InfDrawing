"""Tests for lock compositing, framing checks, and bbox prompt lines."""

from __future__ import annotations

import io

from PIL import Image

from app.controlled_edit.region_ops import (
    bbox_prompt_lines,
    build_edit_mask,
    framing_drift,
    lock_composite,
    uses_local_mask,
)
from app.controlled_edit.schemas import BBox, EditIntent, EntityStatus, SceneEntity


def _png(width: int, height: int, color: tuple[int, int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _pixel(image_bytes: bytes, x: int, y: int) -> tuple[int, int, int]:
    with Image.open(io.BytesIO(image_bytes)) as image:
        return image.convert("RGB").getpixel((x, y))  # type: ignore[return-value]


def test_lock_composite_restores_locked_pixels() -> None:
    parent = _png(100, 100, (10, 20, 30))
    candidate = _png(100, 100, (200, 0, 0))
    entities = [
        SceneEntity(
            id="character.face",
            name="Face",
            status=EntityStatus.LOCKED,
            bbox=BBox(x=0.4, y=0.4, w=0.2, h=0.2),
            anchor_artifact_id="a-face",
        )
    ]
    merged = lock_composite(parent, candidate, entities, target_ids=set(), feather=0.0)
    assert _pixel(merged, 50, 50) == (10, 20, 30)
    assert _pixel(merged, 2, 2) == (200, 0, 0)


def test_lock_composite_skips_cascaded_locks_without_anchor() -> None:
    parent = _png(100, 100, (10, 20, 30))
    candidate = _png(100, 100, (200, 0, 0))
    entities = [
        SceneEntity(
            id="character.face",
            name="Face",
            status=EntityStatus.LOCKED,
            bbox=BBox(x=0.4, y=0.4, w=0.2, h=0.2),
        )
    ]
    merged = lock_composite(parent, candidate, entities, target_ids=set(), feather=0.0)
    assert _pixel(merged, 50, 50) == (200, 0, 0)


def test_framing_drift_detects_zoom() -> None:
    before = [SceneEntity(id="character", name="Character", bbox=BBox(x=0.2, y=0.1, w=0.4, h=0.8))]
    after = [SceneEntity(id="character", name="Character", bbox=BBox(x=0.1, y=0.0, w=0.7, h=0.95))]
    warning = framing_drift(before, after, shift_threshold=0.08, area_threshold=0.15)
    assert warning is not None and "构图偏移" in warning
    same = framing_drift(before, before, shift_threshold=0.08, area_threshold=0.15)
    assert same is None


def test_bbox_prompt_lines_skip_entities_without_box() -> None:
    boxed = SceneEntity(
        id="character.sword",
        name="Sword",
        bbox=BBox(x=0.1, y=0.2, w=0.15, h=0.4),
    )
    bare = SceneEntity(id="environment.sky", name="Sky")
    lines = bbox_prompt_lines([boxed, bare], ["character.sword", "environment.sky"])
    assert len(lines) == 1
    assert "Sword occupies x=0.100, y=0.200, w=0.150, h=0.400" in lines[0]
    assert "full frame" in lines[0]


def test_build_edit_mask_locks_black_and_targets_white() -> None:
    entities = [
        SceneEntity(
            id="character.face",
            name="Face",
            status=EntityStatus.LOCKED,
            bbox=BBox(x=0.0, y=0.0, w=0.5, h=1.0),
        ),
        SceneEntity(
            id="environment.sky",
            name="Sky",
            status=EntityStatus.EDITABLE,
            bbox=BBox(x=0.5, y=0.0, w=0.5, h=1.0),
        ),
    ]
    mask = build_edit_mask((10, 4), entities, ["environment.sky"], unconstrained="keep")
    assert mask.getpixel((1, 2)) == (0, 0, 0)
    assert mask.getpixel((8, 2)) == (255, 255, 255)
    unconstrained = build_edit_mask((10, 4), entities, [], unconstrained="edit")
    assert unconstrained.getpixel((8, 2)) == (255, 255, 255)
    assert unconstrained.getpixel((1, 2)) == (0, 0, 0)


def _intent(*targets: str) -> EditIntent:
    return EditIntent(operation="replace", target_entity_ids=list(targets), change_description="edit")


def test_uses_local_mask_for_small_character_parts() -> None:
    sword = SceneEntity(
        id="character.sword",
        name="Sword",
        bbox=BBox(x=0.1, y=0.2, w=0.15, h=0.4),
    )
    sky = SceneEntity(
        id="environment.sky",
        name="Sky",
        bbox=BBox(x=0.0, y=0.0, w=1.0, h=0.4),
    )
    body = SceneEntity(
        id="character",
        name="Knight",
        bbox=BBox(x=0.2, y=0.0, w=0.5, h=0.99),
    )
    assert uses_local_mask(_intent("character.sword"), [sword, sky, body]) is True
    assert uses_local_mask(_intent("environment.sky"), [sword, sky, body]) is False
    assert uses_local_mask(_intent("character"), [sword, sky, body]) is False
    assert uses_local_mask(_intent(), [sword]) is False
