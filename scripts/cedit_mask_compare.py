#!/usr/bin/env python3
"""Compare Qwen instruction-edit vs Wanx mask inpaint on one controlled-edit frame.

Usage (from repo root):
    backend/.venv/Scripts/python scripts/cedit_mask_compare.py

Probes the official Wanx mask sample first, then runs the knight root frame.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
OFFICIAL_BASE = (
    "http://wanx.alicdn.com/material/20250318/description_edit_with_mask_1.jpeg"
)
OFFICIAL_MASK = (
    "http://wanx.alicdn.com/material/20250318/description_edit_with_mask_1_mask.png"
)
OFFICIAL_PROMPT = "A ceramic rabbit holding a ceramic flower"
DEFAULT_INSTRUCTION = "把背景换成万圣节夜晚：紫色雾气和一轮满月"


def _boot() -> None:
    import os

    os.chdir(BACKEND_ROOT)
    sys.path.insert(0, str(BACKEND_ROOT))


def _write_png(path: Path, image_bytes: bytes) -> None:
    path.write_bytes(image_bytes)


def _label_sheet(images: list[tuple[str, Image.Image]]) -> Image.Image:
    tile = 512
    pad = 16
    header = 28
    width = pad + len(images) * (tile + pad)
    height = pad + header + tile + pad
    sheet = Image.new("RGB", (width, height), (24, 24, 28))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, (title, image) in enumerate(images):
        x = pad + index * (tile + pad)
        draw.text((x, pad), title, fill=(220, 220, 220), font=font)
        fitted = image.convert("RGB").resize((tile, tile), Image.Resampling.LANCZOS)
        sheet.paste(fitted, (x, pad + header))
    return sheet


def _overlay(source: Image.Image, mask: Image.Image) -> Image.Image:
    base = source.convert("RGB")
    mask_l = mask.convert("L").resize(base.size, Image.Resampling.NEAREST)
    tint = Image.blend(base, Image.new("RGB", base.size, (220, 40, 40)), 0.45)
    return Image.composite(tint, base, mask_l)


def _load_version(sessions_path: Path, version_id: str | None) -> dict[str, Any]:
    payload = json.loads(sessions_path.read_text(encoding="utf-8"))
    versions = payload["versions"]
    if version_id:
        for session_versions in versions.values():
            if version_id in session_versions:
                return session_versions[version_id]
        raise KeyError(f"version not found: {version_id}")
    session = next(iter(payload["sessions"].values()))
    root_id = session["root_version_id"]
    return versions[session["id"]][root_id]


def _artifact_path(storage_key: str) -> Path:
    return REPO_ROOT / "data" / "artifacts" / storage_key.replace("\\", "/")


async def _probe_official() -> bytes:
    from app.pipeline.image_providers.dashscope_wanx import DashScopeWanxProvider

    print("probe: official Wanx mask sample")
    provider = DashScopeWanxProvider()
    return await provider.inpaint_from_urls(
        prompt=OFFICIAL_PROMPT,
        base_image_url=OFFICIAL_BASE,
        mask_image_url=OFFICIAL_MASK,
        seed=7,
    )


async def _run_compare(args: argparse.Namespace) -> int:
    _boot()
    from app.controlled_edit.region_ops import build_edit_mask, mask_png_bytes
    from app.controlled_edit.schemas import SceneEntity
    from app.pipeline.image_providers.dashscope_qwen_edit import DashScopeQwenEditProvider
    from app.pipeline.image_providers.dashscope_wanx import DashScopeWanxProvider

    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    notes: dict[str, Any] = {
        "started_at": datetime.now(UTC).isoformat(),
        "instruction": args.instruction,
        "unconstrained": args.unconstrained,
        "targets": args.targets,
    }

    try:
        probe = await _probe_official()
        _write_png(out_dir / "probe_official_wanx.png", probe)
        notes["probe_official"] = "ok"
        print("probe: ok")
    except Exception as exc:
        notes["probe_official"] = f"{type(exc).__name__}: {exc}"
        (out_dir / "notes.json").write_text(
            json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"probe failed: {type(exc).__name__}: {exc}")
        return 1

    version = _load_version(args.sessions, args.version_id)
    artifacts = json.loads(args.artifacts.read_text(encoding="utf-8"))
    record = artifacts["records"][version["image_artifact_id"]]
    source_bytes = _artifact_path(record["storage_key"]).read_bytes()
    source = Image.open(BytesIO(source_bytes)).convert("RGB")
    entities = [SceneEntity.model_validate(item) for item in version["entities"]]
    mask = build_edit_mask(
        source.size,
        entities,
        args.targets,
        unconstrained=args.unconstrained,
    )
    mask_bytes = mask_png_bytes(mask)
    overlay = _overlay(source, mask)
    _write_png(out_dir / "source.png", source_bytes)
    mask.save(out_dir / "mask.png")
    overlay.save(out_dir / "mask_overlay.png")
    notes["version_id"] = version["id"]
    notes["locked"] = [e.id for e in entities if e.status == "locked"]
    hist = mask.convert("L").histogram()
    notes["white_pixels"] = hist[255]
    notes["black_pixels"] = hist[0]

    print("wanx: auto-mask inpaint")
    wanx = DashScopeWanxProvider()
    wanx_bytes = await wanx.inpaint(
        image_bytes=source_bytes,
        mask_bytes=mask_bytes,
        prompt=args.instruction,
        seed=7,
    )
    _write_png(out_dir / "wanx_mask.png", wanx_bytes)
    notes["wanx"] = "ok"

    if not args.skip_qwen:
        print("qwen: instruction edit")
        qwen = DashScopeQwenEditProvider()
        qwen_bytes = await qwen.multi_image_edit(
            image_bytes=source_bytes,
            reference_images=[],
            prompt=args.instruction,
            size=f"{source.width}x{source.height}",
        )
        _write_png(out_dir / "qwen_edit.png", qwen_bytes)
        notes["qwen"] = "ok"
        qwen_im = Image.open(BytesIO(qwen_bytes))
    else:
        qwen_im = Image.new("RGB", source.size, (40, 40, 40))
        notes["qwen"] = "skipped"

    sheet = _label_sheet(
        [
            ("source", source),
            ("mask overlay", overlay),
            ("wanx mask", Image.open(BytesIO(wanx_bytes))),
            ("qwen edit", qwen_im),
        ]
    )
    sheet.save(out_dir / "compare.png")
    notes["finished_at"] = datetime.now(UTC).isoformat()
    (out_dir / "notes.json").write_text(
        json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"wrote {out_dir}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sessions",
        type=Path,
        default=REPO_ROOT / "data" / "cedit" / "sessions.json",
    )
    parser.add_argument(
        "--artifacts",
        type=Path,
        default=REPO_ROOT / "data" / "cedit" / "artifacts.json",
    )
    parser.add_argument("--version-id", default=None)
    parser.add_argument("--instruction", default=DEFAULT_INSTRUCTION)
    parser.add_argument(
        "--unconstrained",
        choices=("edit", "keep"),
        default="edit",
        help="pixels not covered by lock/target boxes",
    )
    parser.add_argument(
        "--target",
        action="append",
        dest="targets",
        default=[],
        help="entity ids painted white (repeatable); empty = background via unconstrained",
    )
    parser.add_argument("--skip-qwen", action="store_true")
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "data" / "logs" / "20261006_cedit_auto_mask",
    )
    args = parser.parse_args()
    return asyncio.run(_run_compare(args))


if __name__ == "__main__":
    raise SystemExit(main())
