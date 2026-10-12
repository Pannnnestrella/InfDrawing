"""Prepare and run a two-image crop/stitch comparison without changing sessions."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import time
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/logs/20261012_local_inpaint_crop_stitch"
PUBLIC = ROOT / "frontend/public/inpaint-comparison"
INSTRUCTION = "将圆形蓝色盾牌改成深红色，保持盾牌原有形状、金属纹理、边框和光照。"


def publish(notes: dict[str, Any]) -> None:
    """Publish the local review page and its experiment assets."""
    (OUT / "report.json").write_text(
        json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    PUBLIC.mkdir(parents=True, exist_ok=True)
    for path in OUT.iterdir():
        if path.suffix in {".png", ".json"}:
            shutil.copy2(path, PUBLIC / path.name)
    shutil.copy2(ROOT / "scripts/templates/inpaint_compare.html", PUBLIC / "index.html")


def prepare() -> None:
    """Segment a real source image and prepare shared inputs without cloud calls."""
    from app.config import settings
    from app.controlled_edit.inpaint_crop import inpaint_crop
    from app.controlled_edit.inpaint_types import InpaintOptions
    from app.controlled_edit.sam2_segmenter import segment_sam2
    from app.controlled_edit.schemas import BBox
    from app.controlled_edit.segmentation import SegmentRequest

    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / "report.json").exists():
        publish(json.loads((OUT / "report.json").read_text(encoding="utf-8")))
        return
    sessions = json.loads((ROOT / "data/cedit/sessions.json").read_text(encoding="utf-8"))
    session = next(s for s in sessions["sessions"].values() if s["title"] == "Two-branch knight")
    version = sessions["versions"][session["id"]][session["root_version_id"]]
    entity = next(e for e in version["entities"] if e["id"] == "character.shield")
    artifacts = json.loads((ROOT / "data/cedit/artifacts.json").read_text(encoding="utf-8"))
    key = artifacts["records"][version["image_artifact_id"]]["storage_key"]
    source = (ROOT / "data/artifacts" / key.replace("\\", "/")).read_bytes()
    box = BBox.model_validate(entity["bbox"])
    candidates = segment_sam2(
        source,
        SegmentRequest(bbox=box, points=[(box.x + box.w / 2, box.y + box.h / 2)], labels=[1]),
        settings,
    )
    nonempty = [(mask, score) for mask, score in candidates if Image.open(BytesIO(mask)).getbbox()]
    if not nonempty:
        raise ValueError("SAM returned no usable shield mask")
    mask, score = max(nonempty, key=lambda item: item[1])
    options = InpaintOptions(dilate_px=4, feather_sigma_px=3)
    crop = inpaint_crop(source, mask, options)
    for name, content in {
        "source.png": source,
        "mask.png": mask,
        "crop.png": crop.image,
        "crop_mask.png": crop.mask,
        "blend.png": crop.blend,
    }.items():
        (OUT / name).write_bytes(content)
    original = Image.open(BytesIO(source)).convert("RGB")
    hard = Image.open(BytesIO(mask)).convert("L")
    tint = Image.blend(original, Image.new("RGB", original.size, (50, 150, 255)), 0.55)
    Image.composite(tint, original, hard).save(OUT / "overlay.png")
    (OUT / "stitcher.json").write_text(crop.stitcher.model_dump_json(indent=2), encoding="utf-8")
    notes = {
        "instruction": INSTRUCTION,
        "source_size": original.size,
        "crop_rect": crop.stitcher.crop_rect,
        "model_size": crop.stitcher.model_size,
        "sam_score": score,
        "mask_source": "SAM 2.1 small / shield box + positive point",
        "estimated_cny": 0.39,
        "scope": "同一改色任务各生成一次，无自动重试",
        "models": {
            "wanx": {
                "name": "wanx2.1-imageedit",
                "status": "pending",
                "mask_mode": "专用二值 Mask 字段",
            },
            "qwen": {
                "name": "qwen-image-2.1-pro",
                "status": "pending",
                "mask_mode": "Mask 作为参考图（实验）",
            },
        },
    }
    publish(notes)
    print(f"Prepared: SAM score={score:.3f}, crop={crop.stitcher.crop_rect}", flush=True)


async def generate(*, followup: bool = False, resume: bool = False) -> None:
    """Attempt at most one output per model, preserving attempts across reruns."""
    from app.config import settings
    from app.controlled_edit.inpaint_stitch import inpaint_stitch
    from app.controlled_edit.inpaint_types import Stitcher
    from app.controlled_edit.masks import png_bytes, prepare_mask
    from app.pipeline.image_providers.base import ImageProviderError
    from app.pipeline.image_providers.dashscope_qwen_edit import (
        DashScopeQwenEditProvider,
    )
    from app.pipeline.image_providers.dashscope_wanx import DashScopeWanxProvider

    notes = json.loads((OUT / "report.json").read_text(encoding="utf-8"))
    stitcher = Stitcher.model_validate_json((OUT / "stitcher.json").read_text(encoding="utf-8"))
    source, crop, mask, blend = [
        (OUT / n).read_bytes() for n in ("source.png", "crop.png", "crop_mask.png", "blend.png")
    ]
    if followup:
        full_mask = png_bytes(
            prepare_mask(
                (OUT / "mask.png").read_bytes(), stitcher.source_size, stitcher.options
            ).hard.convert("RGB")
        )
        (OUT / "full_mask.png").write_bytes(full_mask)
        notes["models"].setdefault(
            "wanx_full",
            {
                "name": "wanx2.1-imageedit · 原图输入",
                "status": "pending",
                "mask_mode": "专用 Mask 字段 · 不裁剪",
                "input_image": "source.png",
                "input_mask": "full_mask.png",
            },
        )
        notes["models"].setdefault(
            "qwen_async",
            {
                "name": "qwen-image-2.1-pro · 异步修复",
                "status": "pending",
                "mask_mode": "Mask 参考图 · 裁剪输入 · 异步任务",
                "input_image": "crop.png",
                "input_mask": "crop_mask.png",
            },
        )
        notes["scope"] = "原裁剪实验 + 万相整图对照 + Qwen 异步修复，各新增一次生成"
        notes["additional_estimated_cny"] = 0.39
        publish(notes)
    for model_id, entry in notes["models"].items():
        if followup and model_id not in {"wanx_full", "qwen_async"}:
            continue
        can_resume = resume and model_id == "qwen_async" and entry.get("task_id")
        if entry["status"] != "pending" and not can_resume:
            continue
        entry["status"] = "running"
        publish(notes)
        started = time.perf_counter()
        print(f"Generating {entry['name']} (one attempt)", flush=True)
        try:
            mapping = stitcher
            if model_id in {"wanx", "wanx_full"}:
                config = settings.model_copy(update={"dashscope_edit_model": "wanx2.1-imageedit"})
                prompt = INSTRUCTION + "仅修改 Mask 白色区域，其他区域保持原样。"
                if model_id == "wanx_full":
                    w, h = stitcher.source_size
                    mapping = stitcher.model_copy(
                        update={
                            "crop_rect": (0, 0, w, h),
                            "paste_rect": (0, 0, w, h),
                            "padding": (0, 0, 0, 0),
                            "canvas_size": (w, h),
                            "model_size": (w, h),
                        }
                    )
                generated = await DashScopeWanxProvider(config).inpaint(
                    image_bytes=source if model_id == "wanx_full" else crop,
                    mask_bytes=full_mask if model_id == "wanx_full" else mask,
                    prompt=prompt,
                    seed=7,
                )
            else:
                config = settings.model_copy(
                    update={
                        "cedit_image_model": "qwen-image-2.1-pro",
                        "cloud_image_timeout_seconds": 600.0,
                    }
                )
                prompt = (
                    "图一是编辑区域的黑白 Mask，白色表示需要修改的区域。图二是待编辑原图。"
                    + INSTRUCTION
                    + "仅修改图二中对应图一白色的区域。保持原图构图，输出完整图二，"
                    "不要输出 Mask 或透明背景。"
                )
                provider = DashScopeQwenEditProvider(config)
                if model_id == "qwen_async":
                    if not can_resume:
                        task = await provider.submit_edit_task(
                            image_bytes=crop,
                            reference_images=[mask],
                            prompt=prompt,
                            size="1024x1024",
                        )
                        entry.update(task)
                        entry["prompt"] = prompt
                        publish(notes)
                        print(f"Saved task_id={task['task_id']}", flush=True)
                    generated = await provider.wait_edit_task(entry["task_id"])
                else:
                    generated = await provider.multi_image_edit(
                        image_bytes=crop, reference_images=[mask], prompt=prompt, size="1024x1024"
                    )
            entry["prompt"] = prompt
            (OUT / f"{model_id}_generated.png").write_bytes(generated)
            entry["output_size"] = Image.open(BytesIO(generated)).size
            final = inpaint_stitch(source, generated, blend, mapping)
            (OUT / f"{model_id}_final.png").write_bytes(final)
            before = np.array(Image.open(BytesIO(source)).convert("RGB"))
            after = np.array(Image.open(BytesIO(final)).convert("RGB"))
            support = np.array(Image.open(BytesIO(blend)).convert("L")) > 0
            delta = np.abs(after.astype(np.int16) - before.astype(np.int16))
            outside = delta[~support]
            entry["outside_changed_pixels"] = int(np.count_nonzero(np.any(outside > 0, axis=1)))
            entry["outside_max_difference"] = int(outside.max()) if outside.size else 0
            if model_id == "wanx_full":
                raw = np.array(Image.open(BytesIO(generated)).convert("RGB"))
                if raw.shape == before.shape:
                    raw_delta = np.abs(raw.astype(np.int16) - before.astype(np.int16))[~support]
                    entry["raw_outside_changed_pixels"] = int(
                        np.count_nonzero(np.any(raw_delta > 0, axis=1))
                    )
                    entry["raw_outside_max_difference"] = int(raw_delta.max())
            entry["inside_mean_difference"] = float(delta[support].mean())
            heat = np.clip(delta.max(axis=2) * 4, 0, 255).astype(np.uint8)
            Image.fromarray(heat).save(OUT / f"{model_id}_difference.png")
            entry["status"] = "complete"
            entry.pop("error", None)
        except (ImageProviderError, ValueError, OSError) as exc:
            entry["status"] = "failed"
            entry["error"] = str(exc).replace(settings.dashscope_api_key, "[redacted]")[:400]
        entry["seconds"] = round(time.perf_counter() - started, 2)
        publish(notes)
        print(f"{entry['name']}: {entry['status']}, {entry['seconds']}s", flush=True)


def main() -> None:
    """Prepare inputs by default; cloud calls require the explicit --generate flag."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generate", action="store_true")
    parser.add_argument(
        "--followup", action="store_true", help="Run the approved full-image/async pair"
    )
    parser.add_argument(
        "--resume", action="store_true", help="Poll the saved Qwen task, no resubmission"
    )
    args = parser.parse_args()
    os.chdir(ROOT / "backend")
    sys.path.insert(0, str(ROOT / "backend"))
    prepare()
    if args.generate or args.followup or args.resume:
        asyncio.run(generate(followup=args.followup or args.resume, resume=args.resume))


if __name__ == "__main__":
    main()
