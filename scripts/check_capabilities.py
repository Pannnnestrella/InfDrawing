#!/usr/bin/env python3
"""Print InfDrawing environment capabilities and remediation hints."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.system.capabilities import gather_capabilities  # noqa: E402


def _print_caps(data: dict) -> None:
    print(f"Tier: {data['tier']}")
    gpu = data["gpu"]
    if gpu.get("available"):
        print(
            f"GPU: {gpu.get('name')} "
            f"({gpu.get('vram_free_mb')} / {gpu.get('vram_total_mb')} MB free)"
        )
    else:
        print("GPU: not detected")

    comfy = data["services"]["comfyui"]
    print(f"ComfyUI: {'OK' if comfy['ok'] else 'DOWN'} @ {comfy['url']}")
    ollama = data["services"]["ollama"]
    print(f"Ollama: {'OK' if ollama['ok'] else 'DOWN'} @ {ollama['url']}")

    print("\nModels:")
    for key, value in data["models"].items():
        mark = "yes" if value else "no"
        print(f"  - {key}: {mark}")

    print("\nFeatures:")
    for name, feature in data["features"].items():
        status = "ENABLED" if feature["enabled"] else "disabled"
        backend = feature.get("backend") or "-"
        reason = feature.get("reason") or ""
        line = f"  - {name}: {status} (backend={backend})"
        if reason:
            line += f" — {reason}"
        print(line)

    if not comfy["ok"]:
        print("\nNext steps:")
        print("  1. Start ComfyUI: python main.py --lowvram --port 8188")
        print("  2. Or set INFD_COMFYUI_BASE_URL to your remote ComfyUI URL")


def main() -> int:
    caps = asyncio.run(gather_capabilities())
    payload = caps.model_dump()
    if "--json" in sys.argv:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        _print_caps(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
