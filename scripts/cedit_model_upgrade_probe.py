"""Paid smoke probe for Qwen 3.0 full-frame and Wan 2.7 bbox local edit."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/logs/20261012_cedit_model_upgrade_probe"
SESSION_TITLE = "Two-branch knight"


def _load_source() -> tuple[bytes, dict]:
    sessions = json.loads((ROOT / "data/cedit/sessions.json").read_text(encoding="utf-8"))
    session = next(s for s in sessions["sessions"].values() if s["title"] == SESSION_TITLE)
    version = sessions["versions"][session["id"]][session["root_version_id"]]
    artifacts = json.loads((ROOT / "data/cedit/artifacts.json").read_text(encoding="utf-8"))
    key = artifacts["records"][version["image_artifact_id"]]["storage_key"]
    source = (ROOT / "data/artifacts" / key.replace("\\", "/")).read_bytes()
    return source, version


async def run_probe() -> None:
    from app.config import settings
    from app.controlled_edit.region_ops import target_pixel_bboxes
    from app.controlled_edit.schemas import BBox, BBoxSource, EntityStatus, SceneEntity
    from app.controlled_edit.sizing import pad_to_supported, restore_original_frame
    from app.pipeline.image_providers.base import ImageProviderError
    from app.pipeline.image_providers.dashscope_qwen_edit import DashScopeQwenEditProvider
    from app.pipeline.image_providers.dashscope_wan27_edit import DashScopeWan27EditProvider

    OUT.mkdir(parents=True, exist_ok=True)
    source, version = _load_source()
    (OUT / "source.png").write_bytes(source)
    report: dict = {"cells": {}}
    entities = [
        SceneEntity(
            id=e["id"],
            name=e.get("name") or e["id"],
            parent_id=e.get("parent_id"),
            description=e.get("description") or "",
            bbox=BBox.model_validate(e["bbox"]) if e.get("bbox") else None,
            bbox_source=BBoxSource.MODEL,
            status=EntityStatus.EDITABLE,
        )
        for e in version["entities"]
    ]
    with Image.open(BytesIO(source)) as im:
        size = im.size
    boxes = target_pixel_bboxes(size, entities, ["character.sword"], max_boxes=1)
    prompt = "将武器换成短刃长刀，保持握持与油画风格、构图不变。"

    async def one(name: str, coro) -> None:
        entry = {"status": "running"}
        report["cells"][name] = entry
        (OUT / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        started = time.perf_counter()
        print(f"generating {name}", flush=True)
        try:
            data = await coro
            path = OUT / f"{name}.png"
            path.write_bytes(data)
            entry.update(
                {
                    "status": "complete",
                    "seconds": round(time.perf_counter() - started, 2),
                    "output_size": list(Image.open(BytesIO(data)).size),
                    "output": path.name,
                }
            )
        except (ImageProviderError, ValueError, OSError) as exc:
            err = str(exc)
            if settings.dashscope_api_key:
                err = err.replace(settings.dashscope_api_key, "[redacted]")
            entry.update(
                {
                    "status": "failed",
                    "error": err[:400],
                    "seconds": round(time.perf_counter() - started, 2),
                }
            )
        (OUT / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"{name}: {entry['status']} {entry['seconds']}s", flush=True)

    config = settings.model_copy(update={"cloud_image_timeout_seconds": 600.0})
    padded = pad_to_supported(source)

    async def qwen3() -> bytes:
        raw = await DashScopeQwenEditProvider(
            config, model="qwen-image-3.0-pro"
        ).multi_image_edit(
            image_bytes=padded.png,
            reference_images=[],
            prompt=prompt + " Keep framing and painterly style.",
            size=padded.size,
        )
        return restore_original_frame(raw, padded)

    async def wan27() -> bytes:
        raw = await DashScopeWan27EditProvider(
            config, model="wan2.7-image-pro"
        ).multi_image_edit(
            image_bytes=source,
            reference_images=[],
            prompt=prompt + "仅修改框选区域。",
            size="2K",
            bbox_list=[boxes],
        )
        with Image.open(BytesIO(source)) as src, Image.open(BytesIO(raw)) as out:
            if out.size != src.size:
                buf = BytesIO()
                out.convert("RGB").resize(src.size, Image.Resampling.LANCZOS).save(
                    buf, format="PNG"
                )
                return buf.getvalue()
        return raw

    report["bbox"] = boxes
    report["prompt"] = prompt
    await one("qwen30_full", qwen3())
    await one("wan27_bbox", wan27())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generate", action="store_true")
    args = parser.parse_args()
    if not args.generate:
        print("Pass --generate to run paid probes.", flush=True)
        return
    os.chdir(ROOT / "backend")
    sys.path.insert(0, str(ROOT / "backend"))
    asyncio.run(run_probe())


if __name__ == "__main__":
    main()
