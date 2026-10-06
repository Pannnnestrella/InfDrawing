#!/usr/bin/env python3
"""Compare scene-parsing bounding boxes from several vision models on the same images.

Usage (from repo root):
    backend/.venv/Scripts/python scripts/cedit_grounding_compare.py IMAGE [IMAGE ...]
        [--models openai:gpt-4o,dashscope:qwen3-vl-plus] [--out DIR]

Every model receives the controlled-edit scene prompt. Boxes are drawn assuming the
``[x_min, y_min, x_max, y_max]`` 0-1000 format; the raw replies are saved alongside so
other coordinate conventions can be checked by hand. Output defaults to
``data/logs/{YYYYMMDD}_cedit_grounding/``.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"

DEFAULT_MODELS = (
    "openai:gpt-4o,dashscope:qwen3-vl-plus,dashscope:qwen3-vl-flash,dashscope:qwen-vl-max"
)
PANEL_SIDE = 640
COLORS = [
    "#ff4d4f", "#40a9ff", "#73d13d", "#ffc53d", "#9254de",
    "#13c2c2", "#f759ab", "#fa8c16", "#2f54eb", "#a0d911",
]


def _load_backend() -> tuple[Any, Any, str]:
    os.chdir(BACKEND_ROOT)
    sys.path.insert(0, str(BACKEND_ROOT))
    from app.config import Settings
    from app.controlled_edit.scene_parser import SCENE_SYSTEM_PROMPT
    from app.controlled_edit.vision import VisionClient

    return Settings(), VisionClient, SCENE_SYSTEM_PROMPT


def _client(spec: str, config: Any, vision_cls: Any) -> Any:
    provider, _, model = spec.partition(":")
    if provider == "openai":
        return vision_cls(config, model=model)
    if provider == "dashscope":
        return vision_cls(
            config,
            base_url=config.cedit_scene_base_url,
            api_key=config.dashscope_api_key,
            model=model,
        )
    raise SystemExit(f"unknown provider in {spec!r}")


async def _parse(client: Any, prompt: str, image: bytes) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        reply = await client.complete_json(
            system_prompt=prompt, user_text="Parse this image.", images=[image]
        )
        error = None
    except Exception as exc:  # noqa: BLE001 - report every model failure in the summary
        reply, error = {}, f"{type(exc).__name__}: {exc}"
    return {"seconds": round(time.perf_counter() - started, 1), "reply": reply, "error": error}


def _panel(image: Image.Image, title: str, result: dict[str, Any]) -> Image.Image:
    panel = image.convert("RGB").copy()
    panel.thumbnail((PANEL_SIDE, PANEL_SIDE))
    draw = ImageDraw.Draw(panel)
    font = ImageFont.load_default()
    w, h = panel.size
    entities = result["reply"].get("entities") or []
    for index, entity in enumerate(entities):
        box = entity.get("box_2d") if isinstance(entity, dict) else None
        if not isinstance(box, list) or len(box) != 4:
            continue
        try:
            x0, y0, x1, y1 = (float(v) / 1000 for v in box)
        except (TypeError, ValueError):
            continue
        color = COLORS[index % len(COLORS)]
        draw.rectangle([x0 * w, y0 * h, x1 * w, y1 * h], outline=color, width=2)
        draw.text((x0 * w + 3, y0 * h + 2), str(entity.get("id")), fill=color, font=font)
    header = f"{title}  ({result['seconds']}s, {len(entities)} entities)"
    if result["error"]:
        header += "  ERROR"
    canvas = Image.new("RGB", (w, h + 18), "white")
    canvas.paste(panel, (0, 18))
    ImageDraw.Draw(canvas).text((4, 3), header, fill="black", font=font)
    return canvas


def _grid(panels: list[Image.Image]) -> Image.Image:
    cols = 2
    rows = (len(panels) + cols - 1) // cols
    cell_w = max(p.width for p in panels)
    cell_h = max(p.height for p in panels)
    grid = Image.new("RGB", (cell_w * cols, cell_h * rows), "white")
    for index, panel in enumerate(panels):
        grid.paste(panel, ((index % cols) * cell_w, (index // cols) * cell_h))
    return grid


async def run(images: list[Path], specs: list[str], out_dir: Path) -> None:
    """Parse every image with every model and write grids plus raw replies."""
    config, vision_cls, prompt_template = _load_backend()
    prompt = prompt_template.format(max_entities=config.cedit_max_entities)
    clients = {spec: _client(spec, config, vision_cls) for spec in specs}
    out_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {"models": specs, "images": {}}
    for path in images:
        data = path.read_bytes()
        results = await asyncio.gather(*(_parse(c, prompt, data) for c in clients.values()))
        by_model = dict(zip(specs, results, strict=True))
        with Image.open(io.BytesIO(data)) as source:
            panels = [_panel(source, spec, result) for spec, result in by_model.items()]
        _grid(panels).save(out_dir / f"{path.stem}_compare.png")
        summary["images"][str(path)] = by_model
        for spec, result in by_model.items():
            count = len(result["reply"].get("entities") or [])
            status = result["error"] or f"{count} entities"
            print(f"{path.name} | {spec}: {result['seconds']}s, {status}")
    (out_dir / "raw_replies.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"Wrote results to {out_dir}")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--models", default=DEFAULT_MODELS)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    out_dir = (args.out or REPO_ROOT / "data" / "logs" / f"{stamp}_cedit_grounding").resolve()
    images = [p.resolve() for p in args.images]
    asyncio.run(run(images, [s.strip() for s in args.models.split(",") if s.strip()], out_dir))


if __name__ == "__main__":
    main()
