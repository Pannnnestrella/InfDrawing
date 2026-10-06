#!/usr/bin/env python3
"""Multi-round Wanx mask edits on small knight parts (sword, shield, gloves)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
OUT_DIR = REPO_ROOT / "data" / "logs" / "20261006_cedit_mask_small"
ROUNDS = [
    ("character.sword", "把长剑换成一把深色木制法杖，顶端嵌一颗绿色水晶"),
    ("character.shield", "把蓝色圆盾换成一只发光的橙色南瓜灯"),
    ("character.gloves", "给皮革手套加上一圈细金线装饰"),
]


def _boot() -> None:
    os.chdir(BACKEND_ROOT)
    sys.path.insert(0, str(BACKEND_ROOT))


def _load_root() -> tuple[bytes, list[Any]]:
    from app.controlled_edit.schemas import SceneEntity

    sessions = json.loads((REPO_ROOT / "data" / "cedit" / "sessions.json").read_text(encoding="utf-8"))
    session = next(iter(sessions["sessions"].values()))
    root = sessions["versions"][session["id"]][session["root_version_id"]]
    artifacts = json.loads((REPO_ROOT / "data" / "cedit" / "artifacts.json").read_text(encoding="utf-8"))
    key = artifacts["records"][root["image_artifact_id"]]["storage_key"]
    path = REPO_ROOT / "data" / "artifacts" / key.replace("\\", "/")
    entities = [SceneEntity.model_validate(item) for item in root["entities"]]
    return path.read_bytes(), entities


def _sheet(images: list[tuple[str, Image.Image]]) -> Image.Image:
    tile, pad, header = 384, 12, 24
    width = pad + len(images) * (tile + pad)
    height = pad + header + tile + pad
    sheet = Image.new("RGB", (width, height), (24, 24, 28))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, (title, image) in enumerate(images):
        x = pad + index * (tile + pad)
        draw.text((x, 8), title, fill=(220, 220, 220), font=font)
        fitted = image.convert("RGB").resize((tile, tile), Image.Resampling.LANCZOS)
        sheet.paste(fitted, (x, pad + header))
    return sheet


def _overlay(source: Image.Image, mask: Image.Image) -> Image.Image:
    base = source.convert("RGB")
    mask_l = mask.convert("L")
    tint = Image.blend(base, Image.new("RGB", base.size, (220, 40, 40)), 0.45)
    return Image.composite(tint, base, mask_l)


async def main() -> int:
    _boot()
    from app.controlled_edit.region_ops import build_edit_mask, mask_png_bytes
    from app.pipeline.image_providers.dashscope_wanx import DashScopeWanxProvider

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    source_bytes, entities = _load_root()
    provider = DashScopeWanxProvider()
    notes: dict[str, Any] = {
        "started_at": datetime.now(UTC).isoformat(),
        "rounds": [],
    }
    frames: list[tuple[str, Image.Image]] = [
        ("source", Image.open(BytesIO(source_bytes)).convert("RGB"))
    ]
    current = source_bytes
    for index, (target_id, instruction) in enumerate(ROUNDS, start=1):
        print(f"round {index}: {target_id} {instruction}")
        source_im = Image.open(BytesIO(current)).convert("RGB")
        mask = build_edit_mask(source_im.size, entities, [target_id], unconstrained="keep")
        overlay = _overlay(source_im, mask)
        overlay.save(OUT_DIR / f"r{index}_mask.png")
        result = await provider.inpaint(
            image_bytes=current,
            mask_bytes=mask_png_bytes(mask),
            prompt=instruction,
            seed=7 + index,
        )
        (OUT_DIR / f"r{index}_out.png").write_bytes(result)
        frames.append((f"r{index} {target_id.split('.')[-1]}", Image.open(BytesIO(result))))
        notes["rounds"].append({"target": target_id, "instruction": instruction, "ok": True})
        current = result
    _sheet(frames).save(OUT_DIR / "compare.png")
    notes["finished_at"] = datetime.now(UTC).isoformat()
    (OUT_DIR / "notes.json").write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
