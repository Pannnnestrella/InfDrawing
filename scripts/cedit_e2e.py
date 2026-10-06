#!/usr/bin/env python3
"""Run a real multi-turn controlled-edit session against a running backend.

Usage (from repo root, backend running on :8000):
    backend/.venv/Scripts/python scripts/cedit_e2e.py [--image path.png]

Without ``--image`` a source image is generated with the configured OpenAI image model.
Results (images, per-turn scores, config) are written to
``data/logs/{YYYYMMDD}_controlled_edit_e2e/``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"

DEFAULT_SOURCE_PROMPT = (
    "Fantasy game concept art, full body: a young female knight in silver armor holding a "
    "sword in her right hand and a round blue shield in her left hand, standing in a green "
    "meadow with flowers, a castle and mountains in the background, clear blue daytime sky, "
    "painterly style, soft daylight"
)
DEFAULT_TURNS = [
    "给角色戴一顶万圣节女巫帽",
    "把背景换成万圣节夜晚：紫色雾气和一轮满月",
    "在角色左侧的地面上加一个发光的南瓜灯",
]
DEFAULT_LOCK_SUFFIXES = ("face", "sword", "shield")
TERMINAL = {"succeeded", "failed"}


def generate_source(prompt: str) -> bytes:
    """Generate a source image with the backend's OpenAI provider."""
    os.chdir(BACKEND_ROOT)
    sys.path.insert(0, str(BACKEND_ROOT))
    from app.pipeline.image_providers.openai_images import OpenAIImageProvider

    return asyncio.run(OpenAIImageProvider().txt2img(prompt=prompt))


def poll_version(
    client: httpx.Client, session_id: str, version_id: str, timeout: float
) -> dict[str, Any]:
    """Poll the session tree until ``version_id`` reaches a terminal status."""
    deadline = time.monotonic() + timeout
    last_step = None
    while time.monotonic() < deadline:
        tree = client.get(f"/sessions/{session_id}").raise_for_status().json()
        version = next(v for v in tree["versions"] if v["id"] == version_id)
        if version["progress_step"] != last_step:
            last_step = version["progress_step"]
            print(f"    step: {last_step or version['status']}")
        if version["status"] in TERMINAL:
            return version
        time.sleep(3)
    raise TimeoutError(f"version {version_id} did not finish within {timeout}s")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, help="source image; generated when omitted")
    parser.add_argument("--api", default="http://127.0.0.1:8000/api/v1/controlled-edit")
    parser.add_argument("--api-key", default=os.environ.get("INFD_E2E_API_KEY", ""))
    parser.add_argument("--turn", action="append", dest="turns", help="instruction (repeatable)")
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "data" / "logs" / f"{datetime.now(UTC):%Y%m%d}_controlled_edit_e2e",
    )
    args = parser.parse_args()
    turns = args.turns or DEFAULT_TURNS
    args.out.mkdir(parents=True, exist_ok=True)

    if args.image:
        source = args.image.read_bytes()
    else:
        print("Generating source image ...")
        source = generate_source(DEFAULT_SOURCE_PROMPT)
    (args.out / "v0_source.png").write_bytes(source)

    headers = {"X-API-Key": args.api_key} if args.api_key else {}
    summary: dict[str, Any] = {"turns": []}
    with httpx.Client(base_url=args.api, headers=headers, timeout=300.0) as client:
        started = time.monotonic()
        created = client.post(
            "/sessions",
            files={"image": ("source.png", source, "image/png")},
            data={"title": "E2E knight"},
        ).raise_for_status().json()
        session_id = created["session"]["id"]
        root = created["versions"][0]
        print(f"Session {session_id}: {len(root['entities'])} entities "
              f"({time.monotonic() - started:.1f}s)")
        for entity in root["entities"]:
            print(f"  - {entity['id']}: {entity['name']}  bbox={entity['bbox']}")
        summary["session_id"] = session_id
        summary["entities"] = root["entities"]

        locked = [
            e["id"] for e in root["entities"] if e["id"].endswith(DEFAULT_LOCK_SUFFIXES)
        ]
        for entity_id in locked:
            client.post(
                f"/sessions/{session_id}/versions/{root['id']}/entities/{entity_id}/status",
                json={"status": "locked"},
            ).raise_for_status()
        print(f"Locked: {locked}")
        summary["locked"] = locked

        parent_id = root["id"]
        for index, instruction in enumerate(turns, start=1):
            print(f"Turn {index}: {instruction}")
            turn_started = time.monotonic()
            response = client.post(
                f"/sessions/{session_id}/turns",
                json={"parent_version_id": parent_id, "instruction": instruction},
            )
            if response.status_code == 409:
                print(f"    conflict: {response.json()['error']['message']}")
                summary["turns"].append({"instruction": instruction, "conflict": response.json()})
                continue
            response.raise_for_status()
            version = poll_version(client, session_id, response.json()["id"], args.timeout)
            elapsed = time.monotonic() - turn_started
            record = {
                "instruction": instruction,
                "version_id": version["id"],
                "status": version["status"],
                "seconds": round(elapsed, 1),
                "attempts": version["attempts"],
                "intent": version["intent"],
                "verification": version["verification"],
                "warnings": version["warnings"],
                "error": version["error"],
                "compiled_prompt": version["compiled_prompt"],
            }
            summary["turns"].append(record)
            verification = version["verification"] or {}
            scores = {p["entity_id"]: p["score"] for p in verification.get("preserved", [])}
            print(f"    {version['status']} in {elapsed:.1f}s, attempts={version['attempts']}, "
                  f"passed={verification.get('passed')}, scores={scores}")
            for warning in version["warnings"]:
                print(f"    ! {warning}")
            if version["status"] != "succeeded":
                break
            image = client.get(f"/artifacts/{version['image_artifact_id']}").raise_for_status()
            (args.out / f"v{index}.png").write_bytes(image.content)
            parent_id = version["id"]

    (args.out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.out / "config.json").write_text(
        json.dumps(
            {"api": args.api, "turns": turns, "lock_suffixes": DEFAULT_LOCK_SUFFIXES},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote results to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
