"""HTTP-level tests for the asset library."""

from __future__ import annotations

import io
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.assets import api as assets_api
from app.assets.caption_parser import CAPTION_SYSTEM_PROMPT
from app.assets.repository import MemoryAssetRepository
from app.assets.service import AssetLibraryService
from app.controlled_edit.vision import VisionError
from app.main import app
from app.production.artifacts import ArtifactService, MemoryArtifactRepository
from app.production.auth import ApiPrincipal, current_principal
from app.production.infrastructure import LocalArtifactStorage
from app.system.capabilities import build_features
from app.system.schemas import ModelsCapability, ServiceStatus


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), (40, 80, 120)).save(buffer, format="PNG")
    return buffer.getvalue()


class StubVision:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    async def complete_json(self, *, system_prompt: str, user_text: str, images=None):  # type: ignore[no-untyped-def]
        self.calls += 1
        if self.fail:
            raise VisionError("no key")
        assert system_prompt == CAPTION_SYSTEM_PROMPT
        return {
            "title": "骑士",
            "objects": ["骑士", "长剑"],
            "tags": ["奇幻"],
            "description": "夜色城堡前的红披风骑士。",
            "style": "电影光，冷色调",
            "asset_type": "character",
            "view": "full_body",
            "genre": "fantasy",
            "background": "environment",
            "pose": "standing",
            "palette": ["红", "金"],
            "materials": ["金属", "布料"],
        }


@pytest.fixture()
def harness(tmp_path: Path) -> Iterator[dict[str, Any]]:
    vision = StubVision()
    service = AssetLibraryService(
        repository=MemoryAssetRepository(),
        artifacts=ArtifactService(MemoryArtifactRepository(), LocalArtifactStorage(tmp_path)),
        vision_factory=lambda: vision,
    )
    state: dict[str, Any] = {"scopes": frozenset({"assets"}), "vision": vision}

    async def principal() -> ApiPrincipal:
        return ApiPrincipal(key_id="key-1", scopes=state["scopes"])

    app.dependency_overrides[current_principal] = principal
    app.dependency_overrides[assets_api._service] = lambda: service
    try:
        with TestClient(app) as client:
            yield {"client": client, "state": state, "service": service, "vision": vision}
    finally:
        app.dependency_overrides.clear()


def test_requires_assets_scope(harness: dict[str, Any]) -> None:
    harness["state"]["scopes"] = frozenset({"generate"})
    response = harness["client"].get("/api/v1/assets/libraries")
    assert response.status_code == 403


def test_ingest_search_patch_and_delete(harness: dict[str, Any]) -> None:
    client: TestClient = harness["client"]
    created_lib = client.post("/api/v1/assets/libraries", json={"name": "角色"})
    assert created_lib.status_code == 201
    library_id = created_lib.json()["id"]

    ingested = client.post(
        "/api/v1/assets/items",
        files={"image": ("a.png", _png(), "image/png")},
        data={"library_id": library_id, "title": ""},
    )
    assert ingested.status_code == 201
    item = ingested.json()
    assert item["title"] == "骑士"
    assert item["caption_status"] == "ok"
    assert "长剑" in item["objects"]
    assert item["asset_type"] == "character"
    assert item["view"] == "full_body"
    assert item["genre"] == "fantasy"

    image = client.get(f"/api/v1/assets/artifacts/{item['artifact_id']}")
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"

    hits = client.get("/api/v1/assets/items", params={"q": "角色", "library_id": library_id})
    assert hits.status_code == 200
    assert [row["id"] for row in hits.json()] == [item["id"]]

    patched = client.patch(
        f"/api/v1/assets/items/{item['id']}",
        json={"tags": ["奇幻", "能用"], "asset_type": "weapon"},
    )
    assert patched.status_code == 200
    assert patched.json()["tags"] == ["奇幻", "能用"]
    assert patched.json()["asset_type"] == "weapon"

    deleted = client.delete(f"/api/v1/assets/items/{item['id']}")
    assert deleted.status_code == 204
    listed = client.get("/api/v1/assets/items")
    assert listed.json() == []


def test_caption_failure_still_persists(harness: dict[str, Any]) -> None:
    harness["vision"].fail = True
    client: TestClient = harness["client"]
    ingested = client.post(
        "/api/v1/assets/items",
        files={"image": ("a.png", _png(), "image/png")},
        data={"title": "手工标题"},
    )
    assert ingested.status_code == 201
    item = ingested.json()
    assert item["title"] == "手工标题"
    assert item["caption_status"] == "caption_failed"
    assert item["caption_error"]


def test_ingest_sniffs_mime_when_content_type_missing(harness: dict[str, Any]) -> None:
    client: TestClient = harness["client"]
    ingested = client.post(
        "/api/v1/assets/items",
        files={"image": ("a.png", _png(), "")},
        data={"title": ""},
    )
    assert ingested.status_code == 201
    assert ingested.json()["caption_status"] == "ok"
    assert ingested.json()["title"] == "骑士"


def test_create_library_with_purpose_and_item_provenance(harness: dict[str, Any]) -> None:
    client: TestClient = harness["client"]
    created = client.post(
        "/api/v1/assets/libraries",
        json={"name": "角色", "purpose": "女骑士概念拆解件"},
    )
    assert created.status_code == 201
    assert created.json()["purpose"] == "女骑士概念拆解件"
    library_id = created.json()["id"]

    patched = client.patch(
        f"/api/v1/assets/libraries/{library_id}",
        json={"purpose": "可复用角色部件"},
    )
    assert patched.status_code == 200
    assert patched.json()["purpose"] == "可复用角色部件"

    ingested = client.post(
        "/api/v1/assets/items",
        files={"image": ("a.png", _png(), "image/png")},
        data={
            "library_id": library_id,
            "keywords": "持剑, 全身",
            "source_project": "骑士demo",
            "character_name": "女剑士",
        },
    )
    assert ingested.status_code == 201
    item = ingested.json()
    assert item["keywords"] == ["持剑", "全身"]
    assert item["source_project"] == "骑士demo"
    assert item["character_name"] == "女剑士"
    assert len(item["content_sha256"]) == 64

    hits = client.get("/api/v1/assets/items", params={"q": "骑士demo"})
    assert hits.status_code == 200
    assert [row["id"] for row in hits.json()] == [item["id"]]


def test_duplicate_ingest_rejected_unless_forced(harness: dict[str, Any]) -> None:
    client: TestClient = harness["client"]
    png = _png()
    first = client.post(
        "/api/v1/assets/items",
        files={"image": ("a.png", png, "image/png")},
        data={"title": ""},
    )
    assert first.status_code == 201
    first_id = first.json()["id"]

    dup = client.post(
        "/api/v1/assets/items",
        files={"image": ("renamed.png", png, "image/png")},
        data={"title": ""},
    )
    assert dup.status_code == 409
    body = dup.json()
    assert body["error"]["code"] == "duplicate_asset"
    assert body["error"]["details"]["existing_id"] == first_id

    forced = client.post(
        "/api/v1/assets/items",
        files={"image": ("renamed.png", png, "image/png")},
        data={"title": "", "force": "true"},
    )
    assert forced.status_code == 201
    assert forced.json()["id"] != first_id
    listed = client.get("/api/v1/assets/items")
    assert len(listed.json()) == 2


def test_asset_library_capability_flag() -> None:
    comfy = ServiceStatus(ok=False, url="http://127.0.0.1:8188")
    models = ModelsCapability()
    off = build_features("cpu_only", comfy, models, dashscope_configured=False)
    assert off["asset_library"].enabled is False
    on = build_features(
        "api_fallback",
        comfy,
        models,
        dashscope_configured=True,
        openai_configured=False,
    )
    assert on["asset_library"].enabled is True
    assert on["asset_library"].backend == "dashscope"
