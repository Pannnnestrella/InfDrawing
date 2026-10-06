#!/usr/bin/env python3
"""Run a two-branch controlled-edit session and archive every turn immediately.

Branch A (from the root): weapon → shield → armor.
Branch B (from the root): hairstyle → hat → background.

Usage (from repo root, backend on :8000):
    backend/.venv/Scripts/python scripts/cedit_two_branch.py --image path.png --out DIR
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from cedit_e2e import poll_version  # noqa: E402

DEFAULT_IMAGE = REPO_ROOT / "data/logs/20261005_controlled_edit_e2e/run3/v0_source.png"
LOCK_SUFFIXES = ("face",)
BRANCH_A = [
    ("a1_weapon", "把角色手里的剑换成一把弯曲的火焰弯刀，其余部分保持不变"),
    ("a2_shield", "把盾牌换成一面带骷髅纹样的黑铁圆盾，其余部分保持不变"),
    ("a3_armor", "把盔甲换成暗金色哥特板甲，其余部分保持不变"),
]
BRANCH_B = [
    ("b1_hair", "把发型改成及腰的金色长卷发，其余部分保持不变"),
    ("b2_hat", "给角色戴一顶带红色羽毛的宽檐帽，其余部分保持不变"),
    ("b3_background", "把背景换成黄昏时分的海边悬崖，其余部分保持不变"),
]


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _save_version_image(client: httpx.Client, version: dict[str, Any], dest: Path) -> None:
    artifact_id = version.get("image_artifact_id")
    if not artifact_id:
        return
    image = client.get(f"/artifacts/{artifact_id}").raise_for_status()
    dest.write_bytes(image.content)


def _run_branch(
    client: httpx.Client,
    session_id: str,
    parent_id: str,
    steps: list[tuple[str, str]],
    timeout: float,
    out_dir: Path,
    summary: dict[str, Any],
) -> None:
    current = parent_id
    for name, instruction in steps:
        print(f"Turn {name}: {instruction}")
        started = time.monotonic()
        response = client.post(
            f"/sessions/{session_id}/turns",
            json={"parent_version_id": current, "instruction": instruction},
        )
        if response.status_code == 409:
            print(f"    conflict: {response.json()['error']['message']}")
            summary["turns"].append({"name": name, "instruction": instruction, "conflict": True})
            _write_json(out_dir / "summary.json", summary)
            continue
        response.raise_for_status()
        version = poll_version(client, session_id, response.json()["id"], timeout)
        elapsed = time.monotonic() - started
        verification = version.get("verification") or {}
        scores = {p["entity_id"]: p["score"] for p in verification.get("preserved", [])}
        print(
            f"    {version['status']} in {elapsed:.1f}s, attempts={version['attempts']}, "
            f"passed={verification.get('passed')}, scores={scores}"
        )
        record = {
            "name": name,
            "instruction": instruction,
            "parent_id": current,
            "version_id": version["id"],
            "status": version["status"],
            "seconds": round(elapsed, 1),
            "attempts": version["attempts"],
            "intent": version.get("intent"),
            "verification": verification,
            "warnings": version.get("warnings"),
            "error": version.get("error"),
        }
        summary["turns"].append(record)
        _write_json(out_dir / "summary.json", summary)
        if version["status"] == "succeeded":
            _save_version_image(client, version, out_dir / f"{name}.png")
            current = version["id"]
        tree = client.get(f"/sessions/{session_id}").raise_for_status().json()
        _write_json(out_dir / "tree.json", tree)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    parser.add_argument("--api", default="http://127.0.0.1:8000/api/v1/controlled-edit")
    parser.add_argument("--api-key", default=os.environ.get("INFD_E2E_API_KEY", ""))
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "data" / "logs" / f"{datetime.now(UTC):%Y%m%d}_cedit_two_branch",
    )
    args = parser.parse_args()
    if not args.image.is_file():
        raise SystemExit(f"source image not found: {args.image}")
    args.out.mkdir(parents=True, exist_ok=True)
    source = args.image.read_bytes()
    (args.out / "v0_source.png").write_bytes(source)

    headers = {"X-API-Key": args.api_key} if args.api_key else {}
    summary: dict[str, Any] = {"turns": [], "branches": {"A": BRANCH_A, "B": BRANCH_B}}
    with httpx.Client(base_url=args.api, headers=headers, timeout=300.0) as client:
        created = client.post(
            "/sessions",
            files={"image": ("source.png", source, "image/png")},
            data={"title": "Two-branch knight"},
        ).raise_for_status().json()
        session_id = created["session"]["id"]
        root = created["versions"][0]
        summary["session_id"] = session_id
        summary["root_version_id"] = root["id"]
        summary["entities"] = root["entities"]
        _write_json(args.out / "summary.json", summary)
        _write_json(args.out / "tree.json", created)
        print(f"Session {session_id}: {len(root['entities'])} entities")
        for entity in root["entities"]:
            print(f"  - {entity['id']}: {entity['name']}")

        locked = [e["id"] for e in root["entities"] if e["id"].endswith(LOCK_SUFFIXES)]
        for entity_id in locked:
            client.post(
                f"/sessions/{session_id}/versions/{root['id']}/entities/{entity_id}/status",
                json={"status": "locked"},
            ).raise_for_status()
        print(f"Locked: {locked}")
        summary["locked"] = locked
        _write_json(args.out / "summary.json", summary)

        print("=== Branch A: weapon / shield / armor ===")
        _run_branch(client, session_id, root["id"], BRANCH_A, args.timeout, args.out, summary)
        print("=== Branch B: hair / hat / background ===")
        client.post(
            f"/sessions/{session_id}/checkout",
            json={"version_id": root["id"]},
        ).raise_for_status()
        _run_branch(client, session_id, root["id"], BRANCH_B, args.timeout, args.out, summary)

        tree = client.get(f"/sessions/{session_id}").raise_for_status().json()
        _write_json(args.out / "tree.json", tree)
        _save_version_image(client, root, args.out / "v0_root.png")

    print(f"Wrote results to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
