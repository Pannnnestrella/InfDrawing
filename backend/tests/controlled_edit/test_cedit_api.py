"""HTTP-level tests: scope gating, error mapping, and the happy path."""

from __future__ import annotations

import io
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import settings
from app.controlled_edit import api as controlled_edit_api
from app.controlled_edit.intent_parser import INTENT_SYSTEM_PROMPT
from app.controlled_edit.repository import MemoryEditRepository
from app.controlled_edit.service import ControlledEditService
from app.main import app
from app.production.artifacts import ArtifactService, MemoryArtifactRepository
from app.production.auth import ApiPrincipal, current_principal
from app.production.infrastructure import LocalArtifactStorage
from app.system.capabilities import build_features
from app.system.schemas import ModelsCapability, ServiceStatus


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (300, 200), (90, 90, 90)).save(buffer, format="PNG")
    return buffer.getvalue()


class StubVision:
    def __init__(self) -> None:
        self.intent: dict[str, Any] = {
            "operation": "replace",
            "target_entity_ids": ["environment.sky"],
            "change_description": "Night sky.",
        }

    async def complete_json(self, *, system_prompt: str, user_text: str, images=None):  # type: ignore[no-untyped-def]
        if system_prompt == INTENT_SYSTEM_PROMPT:
            return self.intent
        return {
            "entities": [
                {"id": "character.face", "name": "Face", "bbox": [0.4, 0.1, 0.2, 0.2]},
                {"id": "environment.sky", "name": "Sky"},
            ]
        }


class StubEditor:
    async def multi_image_edit(self, **_: Any) -> bytes:
        return _png()


@pytest.fixture()
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    vision = StubVision()
    scheduled: list[Any] = []
    service = ControlledEditService(
        repository=MemoryEditRepository(),
        artifacts=ArtifactService(MemoryArtifactRepository(), LocalArtifactStorage(tmp_path)),
        vision_factory=lambda: vision,
        editor_factory=lambda _provider=None: StubEditor(),
        scheduler=scheduled.append,
    )
    state: dict[str, Any] = {"scopes": frozenset({"controlled_edit"})}

    async def principal() -> ApiPrincipal:
        return ApiPrincipal(key_id="key-1", scopes=state["scopes"])

    app.dependency_overrides[current_principal] = principal
    app.dependency_overrides[controlled_edit_api._service] = lambda: service
    try:
        with TestClient(app) as client:
            yield {"client": client, "state": state, "vision": vision, "scheduled": scheduled}
    finally:
        app.dependency_overrides.clear()
        for coro in scheduled:
            coro.close()


def test_requires_controlled_edit_scope(harness: dict[str, Any]) -> None:
    harness["state"]["scopes"] = frozenset({"generate", "artifacts:read"})
    response = harness["client"].get("/api/v1/controlled-edit/sessions")
    assert response.status_code == 403


def test_missing_openai_key_returns_503(
    harness: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "openai_api_key", "")
    response = harness["client"].post(
        "/api/v1/controlled-edit/sessions",
        files={"image": ("a.png", _png(), "image/png")},
    )
    assert response.status_code == 503


def test_session_lock_and_turn_flow(harness: dict[str, Any]) -> None:
    client: TestClient = harness["client"]
    created = client.post(
        "/api/v1/controlled-edit/sessions",
        files={"image": ("a.png", _png(), "image/png")},
        data={"title": "Knight"},
    )
    assert created.status_code == 201
    tree = created.json()
    session_id = tree["session"]["id"]
    root = tree["versions"][0]
    assert tree["session"]["title"] == "Knight"
    assert [e["id"] for e in root["entities"]] == ["character.face", "environment.sky"]

    image = client.get(f"/api/v1/controlled-edit/artifacts/{root['image_artifact_id']}")
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"

    locked = client.post(
        f"/api/v1/controlled-edit/sessions/{session_id}/versions/{root['id']}"
        "/entities/character.face/status",
        json={"status": "locked"},
    )
    assert locked.status_code == 200
    face = next(e for e in locked.json()["entities"] if e["id"] == "character.face")
    assert face["status"] == "locked" and face["anchor_artifact_id"]

    turn = client.post(
        f"/api/v1/controlled-edit/sessions/{session_id}/turns",
        json={"parent_version_id": root["id"], "instruction": "天空换成夜晚"},
    )
    assert turn.status_code == 202
    assert turn.json()["status"] == "pending"
    assert len(harness["scheduled"]) == 1

    harness["vision"].intent = {
        "operation": "restyle",
        "target_entity_ids": ["character.face"],
        "change_description": "Zombie face.",
    }
    conflict = client.post(
        f"/api/v1/controlled-edit/sessions/{session_id}/turns",
        json={"parent_version_id": root["id"], "instruction": "把脸改成僵尸"},
    )
    assert conflict.status_code == 409
    error = conflict.json()["error"]
    assert error["code"] == "lock_conflict"
    assert error["details"]["entities"] == [{"id": "character.face", "name": "Face"}]

    checkout = client.post(
        f"/api/v1/controlled-edit/sessions/{session_id}/checkout",
        json={"version_id": root["id"]},
    )
    assert checkout.status_code == 200
    assert checkout.json()["current_version_id"] == root["id"]

    listed = client.get("/api/v1/controlled-edit/sessions")
    assert [s["id"] for s in listed.json()] == [session_id]


def test_manual_bbox_endpoint(harness: dict[str, Any]) -> None:
    client: TestClient = harness["client"]
    tree = client.post(
        "/api/v1/controlled-edit/sessions",
        files={"image": ("a.png", _png(), "image/png")},
    ).json()
    base = (
        f"/api/v1/controlled-edit/sessions/{tree['session']['id']}"
        f"/versions/{tree['versions'][0]['id']}/entities"
    )

    ok = client.put(
        f"{base}/character.face/bbox", json={"bbox": {"x": 0.3, "y": 0.1, "w": 0.2, "h": 0.25}}
    )
    assert ok.status_code == 200
    face = next(e for e in ok.json()["entities"] if e["id"] == "character.face")
    assert face["bbox_source"] == "manual"
    assert face["bbox"] == pytest.approx({"x": 0.3, "y": 0.1, "w": 0.2, "h": 0.25})

    missing = client.put(
        f"{base}/nope/bbox", json={"bbox": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}}
    )
    assert missing.status_code == 404
    for bad in ({"x": 0.1, "y": 0.1, "w": 0, "h": 0.2}, {"x": 0.9, "y": 0.1, "w": 0.5, "h": 0.2}):
        assert client.put(f"{base}/character.face/bbox", json={"bbox": bad}).status_code == 422


def test_unknown_session_is_404(harness: dict[str, Any]) -> None:
    response = harness["client"].get("/api/v1/controlled-edit/sessions/nope")
    assert response.status_code == 404


def test_capability_follows_openai_key() -> None:
    comfy = ServiceStatus(ok=False, url="http://127.0.0.1:8188")
    models = ModelsCapability()
    on = build_features(
        "cpu_only", comfy, models, dashscope_configured=False, openai_configured=True
    )
    off = build_features("cpu_only", comfy, models, dashscope_configured=False)
    assert on["controlled_edit"].enabled is True
    assert set(on["controlled_edit"].models) == {
        "scene",
        "vision",
        "image",
        "image_provider",
        "image_options",
        "lock_paste",
        "prompt_style",
    }
    assert on["controlled_edit"].models["lock_paste"] == "off"
    assert on["controlled_edit"].models["prompt_style"] == "preserve"
    assert on["controlled_edit"].models["image_provider"] == "openai"
    assert "openai|" in on["controlled_edit"].models["image_options"]
    assert "dashscope|" not in on["controlled_edit"].models["image_options"]
    assert off["controlled_edit"].enabled is False
    assert off["controlled_edit"].reason and "OPENAI" in off["controlled_edit"].reason
