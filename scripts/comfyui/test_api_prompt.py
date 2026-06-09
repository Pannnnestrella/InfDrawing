"""Submit a ComfyUI workflow API JSON and print prompt_id."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import httpx

COMFYUI_URL = "http://127.0.0.1:8188"
WORKFLOW = Path(__file__).resolve().parents[2] / "backend/app/pipeline/workflows/sd15_inpaint_api.json"


def main() -> int:
    workflow = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    client_id = str(uuid.uuid4())
    payload = {"prompt": workflow, "client_id": client_id}
    response = httpx.post(f"{COMFYUI_URL}/prompt", json=payload, timeout=30.0)
    response.raise_for_status()
    data = response.json()
    print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
