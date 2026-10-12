"""Compare edit methods on two two-turn chains (weapon / face).

Methods (independent chains from the same root image):
  1. qwen21_full — qwen-image-2.1-pro full-frame instruction edit
  2. sam_crop_wanx — SAM 2.1 mask → crop → Wanx → stitch
  3. sam_full_wanx — SAM 2.1 mask → full-frame Wanx (no crop)
  4. entity_rect_wanx — entity bbox rectangle mask → full-frame Wanx
  5. sam_qwen21_ref — SAM 2.1 mask as Qwen 2.1 multi-image reference + full frame

Default: prepare masks and overlays only. Use --generate for paid calls.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/logs/20261012_method_compare_weapon_face"

SESSION_TITLE = "Two-branch knight"
METHODS = (
    "qwen21_full",
    "sam_crop_wanx",
    "sam_full_wanx",
    "entity_rect_wanx",
    "sam_qwen21_ref",
)
METHOD_LABELS = {
    "qwen21_full": "Qwen2.1 整图",
    "sam_crop_wanx": "SAM crop→万相",
    "sam_full_wanx": "SAM 整图→万相",
    "entity_rect_wanx": "实体框→万相",
    "sam_qwen21_ref": "SAM→Qwen2.1多图",
}
GROUPS: dict[str, dict[str, Any]] = {
    "weapon": {
        "entity_id": "character.sword",
        "turns": (
            "将武器先换为长刀，保持握持姿势、构图与光照。",
            "将武器再换为水晶匕首，保持握持姿势、构图与光照。",
        ),
    },
    "face": {
        "entity_id": "character.face",
        "turns": (
            "将表情先换为微笑，保持脸部朝向、构图与光照。",
            "将表情再换为大笑，保持脸部朝向、构图与光照。",
        ),
    },
}


def _load_root() -> tuple[bytes, dict[str, Any], dict[str, Any]]:
    sessions = json.loads((ROOT / "data/cedit/sessions.json").read_text(encoding="utf-8"))
    session = next(s for s in sessions["sessions"].values() if s["title"] == SESSION_TITLE)
    version = sessions["versions"][session["id"]][session["root_version_id"]]
    artifacts = json.loads((ROOT / "data/cedit/artifacts.json").read_text(encoding="utf-8"))
    key = artifacts["records"][version["image_artifact_id"]]["storage_key"]
    source = (ROOT / "data/artifacts" / key.replace("\\", "/")).read_bytes()
    return source, version, session


def _entity(version: dict[str, Any], entity_id: str) -> dict[str, Any]:
    return next(e for e in version["entities"] if e["id"] == entity_id)


def _sam_mask(source: bytes, bbox: dict[str, float]) -> tuple[bytes, float]:
    from app.config import settings
    from app.controlled_edit.schemas import BBox
    from app.controlled_edit.sam2_segmenter import segment_sam2
    from app.controlled_edit.segmentation import SegmentRequest

    box = BBox.model_validate(bbox)
    candidates = segment_sam2(
        source,
        SegmentRequest(
            bbox=box,
            points=[(box.x + box.w / 2, box.y + box.h / 2)],
            labels=[1],
        ),
        settings,
    )
    nonempty = [
        (mask, score)
        for mask, score in candidates
        if Image.open(BytesIO(mask)).getbbox()
    ]
    if not nonempty:
        raise ValueError("SAM returned no usable mask")
    return max(nonempty, key=lambda item: item[1])


def _overlay(source: bytes, mask: bytes) -> bytes:
    original = Image.open(BytesIO(source)).convert("RGB")
    hard = Image.open(BytesIO(mask)).convert("L")
    tint = Image.blend(original, Image.new("RGB", original.size, (50, 150, 255)), 0.55)
    buffer = BytesIO()
    Image.composite(tint, original, hard).save(buffer, format="PNG")
    return buffer.getvalue()


def _entity_rect_mask(source: bytes, version: dict[str, Any], entity_id: str) -> bytes:
    from app.controlled_edit.region_ops import build_edit_mask, mask_png_bytes
    from app.controlled_edit.schemas import BBox, BBoxSource, EntityStatus, SceneEntity

    with Image.open(BytesIO(source)) as im:
        size = im.size
    entities = []
    for raw in version["entities"]:
        bbox = BBox.model_validate(raw["bbox"]) if raw.get("bbox") else None
        entities.append(
            SceneEntity(
                id=raw["id"],
                name=raw.get("name") or raw["id"],
                parent_id=raw.get("parent_id"),
                description=raw.get("description") or "",
                bbox=bbox,
                bbox_source=BBoxSource.MODEL,
                status=EntityStatus(raw.get("status") or "editable"),
            )
        )
    return mask_png_bytes(
        build_edit_mask(size, entities, [entity_id], unconstrained="keep")
    )


def _cell_key(group: str, method: str, turn: int) -> str:
    return f"{group}.{method}.t{turn}"


def _write_report(notes: dict[str, Any]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.json").write_text(
        json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def ensure_cells(notes: dict[str, Any]) -> dict[str, Any]:
    """Add any missing method/turn cells without resetting completed work."""
    for group_id, spec in GROUPS.items():
        notes.setdefault("groups", {}).setdefault(
            group_id,
            {"entity_id": spec["entity_id"], "turns": list(spec["turns"])},
        )
        for method in METHODS:
            for turn in (1, 2):
                key = _cell_key(group_id, method, turn)
                notes.setdefault("cells", {}).setdefault(
                    key,
                    {
                        "group": group_id,
                        "method": method,
                        "turn": turn,
                        "instruction": spec["turns"][turn - 1],
                        "status": "pending",
                        "output": f"{group_id}/{method}_t{turn}.png",
                    },
                )
    _write_report(notes)
    return notes


def prepare() -> dict[str, Any]:
    """Segment root masks and initialize the report skeleton."""
    if (OUT / "report.json").exists():
        return ensure_cells(
            json.loads((OUT / "report.json").read_text(encoding="utf-8"))
        )

    source, version, session = _load_root()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "source.png").write_bytes(source)
    with Image.open(BytesIO(source)) as im:
        source_size = list(im.size)

    notes: dict[str, Any] = {
        "session_title": SESSION_TITLE,
        "session_id": session["id"],
        "root_version_id": session["root_version_id"],
        "source_size": source_size,
        "scope": "两组×四方法×两轮；每格最多一次付费提交；不写回 Studio 会话",
        "groups": {},
        "cells": {},
    }
    for group_id, spec in GROUPS.items():
        entity = _entity(version, spec["entity_id"])
        gdir = OUT / group_id
        gdir.mkdir(parents=True, exist_ok=True)
        sam_mask, score = _sam_mask(source, entity["bbox"])
        (gdir / "sam_mask_t1.png").write_bytes(sam_mask)
        (gdir / "sam_overlay_t1.png").write_bytes(_overlay(source, sam_mask))
        rect = _entity_rect_mask(source, version, spec["entity_id"])
        (gdir / "entity_mask_t1.png").write_bytes(rect)
        (gdir / "entity_overlay_t1.png").write_bytes(_overlay(source, rect))
        notes["groups"][group_id] = {
            "entity_id": spec["entity_id"],
            "turns": list(spec["turns"]),
            "bbox": entity["bbox"],
            "sam_score_t1": score,
        }
        for method in METHODS:
            for turn in (1, 2):
                key = _cell_key(group_id, method, turn)
                notes["cells"][key] = {
                    "group": group_id,
                    "method": method,
                    "turn": turn,
                    "instruction": spec["turns"][turn - 1],
                    "status": "pending",
                    "output": f"{group_id}/{method}_t{turn}.png",
                }
    _write_report(notes)
    print(f"Prepared under {OUT}", flush=True)
    return notes


async def _run_qwen(parent: bytes, instruction: str) -> bytes:
    from app.config import settings
    from app.controlled_edit.sizing import pad_to_supported, restore_original_frame
    from app.pipeline.image_providers.dashscope_qwen_edit import DashScopeQwenEditProvider

    padded = pad_to_supported(parent)
    config = settings.model_copy(
        update={
            "cedit_image_model": "qwen-image-2.1-pro",
            "cloud_image_timeout_seconds": 600.0,
        }
    )
    raw = await DashScopeQwenEditProvider(config).multi_image_edit(
        image_bytes=padded.png,
        reference_images=[],
        prompt=instruction + " Keep framing, identity, and lighting. Output the full scene.",
        size=padded.size,
    )
    return restore_original_frame(raw, padded)


def _qwen21_mask_guide(parent: bytes, hard_mask: Image.Image) -> bytes:
    """Build image1: same scene as parent with a rough edit mask tint (Comfy-style)."""
    original = Image.open(BytesIO(parent)).convert("RGB")
    tint = Image.new("RGB", original.size, (255, 255, 255))
    # Rough guide: wash the editable region toward white so the mask reads as “to replace”.
    guide = Image.composite(
        Image.blend(original, tint, 0.55),
        original,
        hard_mask.convert("L"),
    )
    buffer = BytesIO()
    guide.save(buffer, format="PNG")
    return buffer.getvalue()


def qwen21_mask_edit_prompt(instruction: str, *, allow_alpha: bool = True) -> str:
    """Prompt for Qwen 2.1 dual-image rough-mask edits (delegates to controlled_edit)."""
    from app.controlled_edit.qwen_mask_prompt import qwen_mask_edit_prompt

    return qwen_mask_edit_prompt(instruction, allow_alpha=allow_alpha)


async def _run_sam_qwen_ref(parent: bytes, mask: bytes, instruction: str) -> bytes:
    """Qwen 2.1: image1 = rough masked guide, image2 = clean parent (primary last)."""
    from app.config import settings
    from app.controlled_edit.alpha import has_meaningful_alpha
    from app.controlled_edit.inpaint_types import InpaintOptions
    from app.controlled_edit.masks import prepare_mask
    from app.controlled_edit.qwen_mask_prompt import wants_transparency
    from app.controlled_edit.sizing import pad_to_supported, restore_original_frame
    from app.pipeline.image_providers.dashscope_qwen_edit import DashScopeQwenEditProvider

    with Image.open(BytesIO(parent)) as im:
        size = im.size
    prepared = prepare_mask(
        mask, size, InpaintOptions(dilate_px=4, feather_sigma_px=0, placement="fullframe")
    )
    guide = _qwen21_mask_guide(parent, prepared.hard)
    allow_alpha = wants_transparency(instruction, parent_has_alpha=has_meaningful_alpha(parent))
    padded = pad_to_supported(parent, keep_alpha=allow_alpha)
    prompt = qwen21_mask_edit_prompt(instruction, allow_alpha=allow_alpha)
    config = settings.model_copy(
        update={
            "cedit_image_model": "qwen-image-2.1-pro",
            "cloud_image_timeout_seconds": 600.0,
        }
    )
    raw = await DashScopeQwenEditProvider(config).multi_image_edit(
        image_bytes=padded.png,
        reference_images=[guide],
        prompt=prompt,
        size=padded.size,
    )
    return restore_original_frame(raw, padded)


async def _run_sam_crop(parent: bytes, mask: bytes, instruction: str) -> bytes:
    from app.config import settings
    from app.controlled_edit.inpaint_crop import inpaint_crop
    from app.controlled_edit.inpaint_stitch import inpaint_stitch
    from app.controlled_edit.inpaint_types import InpaintOptions
    from app.pipeline.image_providers.dashscope_wanx import DashScopeWanxProvider

    options = InpaintOptions(dilate_px=4, feather_sigma_px=3, placement="crop")
    crop = inpaint_crop(parent, mask, options)
    prompt = instruction + "仅修改 Mask 白色区域，其他区域保持原样。"
    config = settings.model_copy(update={"dashscope_edit_model": "wanx2.1-imageedit"})
    generated = await DashScopeWanxProvider(config).inpaint(
        image_bytes=crop.image, mask_bytes=crop.mask, prompt=prompt, seed=7
    )
    return inpaint_stitch(parent, generated, crop.blend, crop.stitcher)


async def _run_sam_full(parent: bytes, mask: bytes, instruction: str) -> bytes:
    from app.config import settings
    from app.controlled_edit.inpaint_types import InpaintOptions
    from app.controlled_edit.masks import prepare_mask
    from app.controlled_edit.region_ops import mask_png_bytes
    from app.pipeline.image_providers.dashscope_wanx import DashScopeWanxProvider

    with Image.open(BytesIO(parent)) as im:
        size = im.size
    options = InpaintOptions(dilate_px=4, feather_sigma_px=3, placement="fullframe")
    prepared = prepare_mask(mask, size, options)
    prompt = instruction + "仅修改 Mask 白色区域，其他区域保持原样。"
    config = settings.model_copy(update={"dashscope_edit_model": "wanx2.1-imageedit"})
    return await DashScopeWanxProvider(config).inpaint(
        image_bytes=parent,
        mask_bytes=mask_png_bytes(prepared.hard),
        prompt=prompt,
        seed=7,
    )


async def _run_entity_rect(
    parent: bytes, version: dict[str, Any], entity_id: str, instruction: str
) -> bytes:
    from app.config import settings
    from app.pipeline.image_providers.dashscope_wanx import DashScopeWanxProvider

    mask = _entity_rect_mask(parent, version, entity_id)
    prompt = instruction + "仅修改 Mask 白色区域，其他区域保持原样。"
    config = settings.model_copy(update={"dashscope_edit_model": "wanx2.1-imageedit"})
    return await DashScopeWanxProvider(config).inpaint(
        image_bytes=parent, mask_bytes=mask, prompt=prompt, seed=7
    )


def _parent_for_cell(
    notes: dict[str, Any], group: str, method: str, turn: int
) -> bytes:
    if turn == 1:
        return (OUT / "source.png").read_bytes()
    prev = notes["cells"][_cell_key(group, method, 1)]
    if prev["status"] != "complete":
        raise RuntimeError(f"turn1 not complete for {group}/{method}")
    return (OUT / prev["output"]).read_bytes()


def _mask_for_turn(
    group: str, turn: int, parent: bytes, bbox: dict[str, float]
) -> bytes:
    gdir = OUT / group
    if turn == 1 and (gdir / "sam_mask_t1.png").exists():
        return (gdir / "sam_mask_t1.png").read_bytes()
    mask, score = _sam_mask(parent, bbox)
    path = gdir / f"sam_mask_t{turn}.png"
    path.write_bytes(mask)
    (gdir / f"sam_overlay_t{turn}.png").write_bytes(_overlay(parent, mask))
    print(f"  re-SAM {group} t{turn} score={score:.3f}", flush=True)
    return mask


async def generate(
    *,
    resume: bool = False,
    groups: set[str] | None = None,
    methods: set[str] | None = None,
) -> None:
    """Run pending cells; skip completed unless not resume-only pending."""
    from app.config import settings
    from app.pipeline.image_providers.base import ImageProviderError

    notes = prepare()
    _, version, _ = _load_root()
    for key, cell in notes["cells"].items():
        if groups is not None and cell["group"] not in groups:
            continue
        if methods is not None and cell["method"] not in methods:
            continue
        if cell["status"] == "complete":
            continue
        if resume and cell["status"] not in {"pending", "failed"}:
            continue
        group = cell["group"]
        method = cell["method"]
        turn = cell["turn"]
        if turn == 2:
            prev = notes["cells"][_cell_key(group, method, 1)]
            if prev["status"] != "complete":
                print(f"skip {key}: turn1 incomplete", flush=True)
                continue
        cell["status"] = "running"
        _write_report(notes)
        started = time.perf_counter()
        print(f"generating {key}", flush=True)
        try:
            parent = _parent_for_cell(notes, group, method, turn)
            instruction = cell["instruction"]
            bbox = notes["groups"][group]["bbox"]
            entity_id = notes["groups"][group]["entity_id"]
            if method == "qwen21_full":
                result = await _run_qwen(parent, instruction)
            elif method == "sam_crop_wanx":
                mask = _mask_for_turn(group, turn, parent, bbox)
                result = await _run_sam_crop(parent, mask, instruction)
            elif method == "sam_full_wanx":
                mask = _mask_for_turn(group, turn, parent, bbox)
                result = await _run_sam_full(parent, mask, instruction)
            elif method == "entity_rect_wanx":
                result = await _run_entity_rect(parent, version, entity_id, instruction)
            elif method == "sam_qwen21_ref":
                mask = _mask_for_turn(group, turn, parent, bbox)
                result = await _run_sam_qwen_ref(parent, mask, instruction)
            else:
                raise ValueError(method)
            out_path = OUT / cell["output"]
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(result)
            cell["status"] = "complete"
            cell["output_size"] = list(Image.open(BytesIO(result)).size)
            cell.pop("error", None)
        except (ImageProviderError, ValueError, OSError, RuntimeError) as exc:
            cell["status"] = "failed"
            err = str(exc)
            if settings.dashscope_api_key:
                err = err.replace(settings.dashscope_api_key, "[redacted]")
            cell["error"] = err[:400]
        cell["seconds"] = round(time.perf_counter() - started, 2)
        _write_report(notes)
        print(f"{key}: {cell['status']} {cell['seconds']}s", flush=True)
    build_grids(notes)


def _thumb(path: Path, size: tuple[int, int]) -> Image.Image:
    if not path.exists():
        img = Image.new("RGB", size, (40, 40, 40))
        draw = ImageDraw.Draw(img)
        draw.text((12, 12), "missing", fill=(200, 80, 80))
        return img
    img = Image.open(path).convert("RGB")
    img.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, (20, 20, 20))
    canvas.paste(img, ((size[0] - img.width) // 2, (size[1] - img.height) // 2))
    return canvas


def build_grids(notes: dict[str, Any] | None = None) -> None:
    """Merge per-group and all-group comparison sheets."""
    if notes is None:
        notes = ensure_cells(
            json.loads((OUT / "report.json").read_text(encoding="utf-8"))
        )
    cell_w, cell_h = 320, 180
    label_h = 28
    font = ImageFont.load_default()
    sheets: list[Image.Image] = []
    for group_id in GROUPS:
        methods = [
            m
            for m in METHODS
            if _cell_key(group_id, m, 1) in notes["cells"]
            and notes["cells"][_cell_key(group_id, m, 1)].get("status") == "complete"
        ] or list(METHODS)
        cols = 3  # source | t1 | t2
        rows = len(methods)
        sheet = Image.new(
            "RGB", (cell_w * cols + 160, cell_h * rows + label_h + 8), (12, 12, 12)
        )
        draw = ImageDraw.Draw(sheet)
        draw.text((8, 6), f"{group_id} · 原图 | Turn1 | Turn2", fill=(230, 230, 230), font=font)
        for row, method in enumerate(methods):
            y = label_h + row * cell_h
            draw.text((8, y + 8), METHOD_LABELS[method], fill=(200, 200, 120), font=font)
            images = [
                OUT / "source.png",
                OUT / notes["cells"][_cell_key(group_id, method, 1)]["output"],
                OUT / notes["cells"][_cell_key(group_id, method, 2)]["output"],
            ]
            for col, path in enumerate(images):
                thumb = _thumb(path, (cell_w - 4, cell_h - 4))
                sheet.paste(thumb, (160 + col * cell_w + 2, y + 2))
        out = OUT / f"compare_{group_id}.png"
        sheet.save(out)
        sheets.append(sheet)
        print(f"Wrote {out}", flush=True)
    total_h = sum(s.height for s in sheets) + 16
    width = max(s.width for s in sheets)
    all_sheet = Image.new("RGB", (width, total_h), (8, 8, 8))
    y = 8
    for sheet in sheets:
        all_sheet.paste(sheet, (0, y))
        y += sheet.height + 8
    all_path = OUT / "compare_all.png"
    all_sheet.save(all_path)
    print(f"Wrote {all_path}", flush=True)
    notes["compare"] = {
        "weapon": "compare_weapon.png",
        "face": "compare_face.png",
        "all": "compare_all.png",
    }
    _write_report(notes)


def main() -> None:
    """Prepare by default; cloud calls require --generate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--grid-only", action="store_true")
    parser.add_argument("--group", action="append", choices=list(GROUPS), default=None)
    parser.add_argument("--method", action="append", choices=list(METHODS), default=None)
    args = parser.parse_args()
    os.chdir(ROOT / "backend")
    sys.path.insert(0, str(ROOT / "backend"))
    if args.grid_only:
        build_grids()
        return
    prepare()
    if args.generate or args.resume:
        asyncio.run(
            generate(
                resume=args.resume,
                groups=set(args.group) if args.group else None,
                methods=set(args.method) if args.method else None,
            )
        )


if __name__ == "__main__":
    main()
