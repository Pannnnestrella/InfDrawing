"""Region helpers: optional lock paste, framing checks, and bbox prompt lines."""

from __future__ import annotations

import io
from collections.abc import Sequence
from typing import Literal

from PIL import Image, ImageDraw, ImageFilter

from app.controlled_edit.anchors import padded_pixel_rect
from app.controlled_edit.schemas import BBox, EditIntent, EntityStatus, SceneEntity

UnconstrainedFill = Literal["edit", "keep"]
_WHITE = (255, 255, 255)
_BLACK = (0, 0, 0)


def lock_composite(
    parent_bytes: bytes,
    candidate_bytes: bytes,
    entities: list[SceneEntity],
    target_ids: set[str],
    *,
    feather: float = 0.12,
    anchored_only: bool = True,
) -> bytes:
    """Copy locked, non-target boxes from the parent onto the candidate.

    Args:
        anchored_only: When True (default), only entities with an anchor crop are
            pasted. Cascaded child locks without their own anchors are skipped.
    """
    result = candidate_bytes
    for entity in entities:
        if entity.status != EntityStatus.LOCKED or entity.id in target_ids:
            continue
        if entity.bbox is None:
            continue
        if anchored_only and not entity.anchor_artifact_id:
            continue
        result = _blend_region(result, parent_bytes, entity.bbox, feather)
    return result


def framing_drift(
    previous: list[SceneEntity],
    current: list[SceneEntity],
    *,
    shift_threshold: float,
    area_threshold: float,
) -> str | None:
    """Describe subject-box drift, or None when framing is stable."""
    subject_id = _subject_id(previous)
    if subject_id is None:
        return None
    by_prev = {entity.id: entity for entity in previous}
    by_cur = {entity.id: entity for entity in current}
    before = by_prev.get(subject_id)
    after = by_cur.get(subject_id)
    if before is None or after is None or before.bbox is None or after.bbox is None:
        return None
    shift = _center_shift(before.bbox, after.bbox)
    area_delta = abs(_area(after.bbox) - _area(before.bbox)) / max(_area(before.bbox), 1e-6)
    if shift < shift_threshold and area_delta < area_threshold:
        return None
    return (
        f"主体「{after.name}」构图偏移（位移 {shift:.2f}，面积变化 {area_delta:.2f}），"
        "请保持与上一版相同的位置和大小"
    )


def build_edit_mask(
    size: tuple[int, int],
    entities: Sequence[SceneEntity],
    target_ids: Sequence[str],
    *,
    unconstrained: UnconstrainedFill = "edit",
) -> Image.Image:
    """Build a Wanx-style RGB mask: white is editable, black must stay.

    Locked and approved boxes are painted black. Target boxes are painted white
    last so they win even if they overlap a lock (the caller should already have
    rejected lock conflicts). Pixels not covered by any box follow
    ``unconstrained``.
    """
    fill = _WHITE if unconstrained == "edit" else _BLACK
    mask = Image.new("RGB", size, fill)
    draw = ImageDraw.Draw(mask)
    keep_ids = {
        entity.id
        for entity in entities
        if entity.status in {EntityStatus.LOCKED, EntityStatus.APPROVED} and entity.bbox
    }
    for entity in entities:
        if entity.id not in keep_ids or entity.bbox is None:
            continue
        box = padded_pixel_rect(size, entity.bbox, padding=0.0)
        draw.rectangle([box[0], box[1], box[2] - 1, box[3] - 1], fill=_BLACK)
    by_id = {entity.id: entity for entity in entities}
    for entity_id in target_ids:
        entity = by_id.get(entity_id)
        if entity is None or entity.bbox is None:
            continue
        box = padded_pixel_rect(size, entity.bbox, padding=0.0)
        draw.rectangle([box[0], box[1], box[2] - 1, box[3] - 1], fill=_WHITE)
    return mask


def uses_local_mask(intent: EditIntent, entities: Sequence[SceneEntity]) -> bool:
    """Return True when the turn should use a small-object mask inpaint.

    Background, whole-subject, missing boxes, or large boxes stay on full-frame
    instruction edit. Small ``character.*`` parts with boxes use the mask path.
    """
    by_id = {entity.id: entity for entity in entities}
    targets = [entity_id for entity_id in intent.target_entity_ids if entity_id in by_id]
    if not targets:
        return False
    for entity_id in targets:
        if _is_background_id(entity_id) or _is_whole_subject_id(entity_id):
            return False
        entity = by_id[entity_id]
        if entity.bbox is None:
            return False
        if _area(entity.bbox) > 0.25:
            return False
    return True


def _is_background_id(entity_id: str) -> bool:
    root = entity_id.split(".", 1)[0]
    return root in {"environment", "foreground"}


def _is_whole_subject_id(entity_id: str) -> bool:
    return "." not in entity_id and not _is_background_id(entity_id)


def mask_png_bytes(mask: Image.Image) -> bytes:
    """Encode an RGB mask as PNG bytes."""
    buffer = io.BytesIO()
    mask.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def bbox_prompt_lines(entities: list[SceneEntity], target_ids: list[str]) -> list[str]:
    """Describe target boxes so the image model knows where to edit."""
    by_id = {entity.id: entity for entity in entities}
    lines: list[str] = []
    for entity_id in target_ids:
        entity = by_id.get(entity_id)
        if entity is None or entity.bbox is None:
            continue
        box = entity.bbox
        lines.append(
            f"{entity.name} occupies x={box.x:.3f}, y={box.y:.3f}, "
            f"w={box.w:.3f}, h={box.h:.3f} of the current image (normalized 0-1). "
            "Change only this region; leave the rest of the full frame unchanged."
        )
    return lines


def _subject_id(entities: list[SceneEntity]) -> str | None:
    ids = {entity.id for entity in entities}
    if "character" in ids:
        return "character"
    candidates = [
        entity
        for entity in entities
        if entity.bbox is not None and not entity.id.startswith("environment")
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda entity: _area(entity.bbox) if entity.bbox else 0.0).id


def _area(box: BBox) -> float:
    return box.w * box.h


def _center_shift(before: BBox, after: BBox) -> float:
    dx = (after.x + after.w / 2) - (before.x + before.w / 2)
    dy = (after.y + after.h / 2) - (before.y + before.h / 2)
    return (dx * dx + dy * dy) ** 0.5


def _blend_region(dst: bytes, src: bytes, bbox: BBox, feather: float) -> bytes:
    with Image.open(io.BytesIO(dst)) as dest_im, Image.open(io.BytesIO(src)) as src_im:
        dest_rgb = dest_im.convert("RGB")
        src_rgb = src_im.convert("RGB")
        if src_rgb.size != dest_rgb.size:
            src_rgb = src_rgb.resize(dest_rgb.size, Image.Resampling.LANCZOS)
        box = padded_pixel_rect(dest_rgb.size, bbox, padding=0.0)
        return _blend(dest_rgb, src_rgb, box, feather)


def _blend(
    dest: Image.Image,
    src: Image.Image,
    box: tuple[int, int, int, int],
    feather: float,
) -> bytes:
    mask = Image.new("L", dest.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rectangle([box[0], box[1], box[2] - 1, box[3] - 1], fill=255)
    radius = max(1.0, min(box[2] - box[0], box[3] - box[1]) * feather / 2)
    mask = mask.filter(ImageFilter.GaussianBlur(radius=radius))
    merged = Image.composite(src, dest, mask)
    buffer = io.BytesIO()
    merged.save(buffer, format="PNG")
    return buffer.getvalue()
