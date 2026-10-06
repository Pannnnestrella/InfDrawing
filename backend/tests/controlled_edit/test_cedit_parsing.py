"""Tests for the vision client, scene parser, and intent parser."""

from __future__ import annotations

import asyncio
import io
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from PIL import Image

from app.config import Settings
from app.controlled_edit.intent_parser import parse_intent
from app.controlled_edit.scene_parser import (
    SceneParseError,
    entities_from_reply,
    parse_scene,
)
from app.controlled_edit.schemas import EditOperation, EntityStatus, SceneEntity
from app.controlled_edit.vision import (
    VisionClient,
    VisionError,
    scene_model_name,
    scene_vision_client,
)


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def _png(width: int = 64, height: int = 32) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (200, 50, 50)).save(buffer, format="PNG")
    return buffer.getvalue()


class FakeModel:
    """Records calls and returns a canned JSON reply."""

    def __init__(self, reply: dict[str, Any]) -> None:
        self.reply = reply
        self.calls: list[dict[str, Any]] = []

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_text: str,
        images: list[bytes] | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {"system_prompt": system_prompt, "user_text": user_text, "images": images or []}
        )
        return self.reply


SCENE_REPLY = {
    "entities": [
        {"id": "character", "name": "Character", "parent_id": None, "bbox": [0.3, 0.1, 0.4, 0.8]},
        {
            "id": "character.face",
            "name": "Face",
            "parent_id": "character",
            "description": "pale face, green eyes",
            "bbox": [0.45, 0.15, 0.1, 0.1],
        },
        {"id": "environment.sky", "name": "Sky", "parent_id": "environment", "bbox": None},
    ]
}


def test_parse_scene_validates_and_fixes_orphans() -> None:
    model = FakeModel(SCENE_REPLY)
    entities = _run(parse_scene(model, _png()))
    assert [e.id for e in entities] == ["character", "character.face", "environment.sky"]
    assert entities[1].bbox is not None and entities[1].bbox.w == pytest.approx(0.1)
    assert entities[2].parent_id is None
    assert all(e.status == EntityStatus.EDITABLE for e in entities)
    assert len(model.calls[0]["images"]) == 1


def test_box_2d_corners_on_1000_grid_are_normalized() -> None:
    entities = entities_from_reply(
        {"entities": [{"id": "character.sword", "name": "Sword", "box_2d": [80, 50, 300, 570]}]}
    )
    bbox = entities[0].bbox
    assert bbox is not None
    assert (bbox.x, bbox.y) == pytest.approx((0.08, 0.05))
    assert (bbox.w, bbox.h) == pytest.approx((0.22, 0.52))
    with pytest.raises(SceneParseError, match="'character.sword'"):
        entities_from_reply(
            {"entities": [{"id": "character.sword", "name": "Sword", "box_2d": [300, 50, 80]}]}
        )


def test_box_2d_yxyx_1000_and_pixel_formats() -> None:
    yxyx = entities_from_reply(
        {"entities": [{"id": "face", "name": "Face", "box_2d": [50, 80, 200, 300]}]},
        box_format="yxyx_1000",
    )[0].bbox
    assert yxyx is not None
    assert (yxyx.x, yxyx.y) == pytest.approx((0.08, 0.05))
    assert (yxyx.w, yxyx.h) == pytest.approx((0.22, 0.15))

    pixel = entities_from_reply(
        {"entities": [{"id": "face", "name": "Face", "box_2d": [80, 40, 240, 200]}]},
        box_format="xyxy_pixel",
        image_size=(400, 200),
    )[0].bbox
    assert pixel is not None
    assert (pixel.x, pixel.y) == pytest.approx((0.2, 0.2))
    assert (pixel.w, pixel.h) == pytest.approx((0.4, 0.8))

    with pytest.raises(SceneParseError, match="image size"):
        entities_from_reply(
            {"entities": [{"id": "face", "name": "Face", "box_2d": [1, 1, 2, 2]}]},
            box_format="xyxy_pixel",
        )
    with pytest.raises(SceneParseError, match="unknown box format"):
        entities_from_reply(
            {"entities": [{"id": "face", "name": "Face", "box_2d": [1, 1, 2, 2]}]},
            box_format="polar",
        )


def test_reparse_sends_previous_ids() -> None:
    model = FakeModel(SCENE_REPLY)
    previous = [SceneEntity(id="character.face", name="Face", description="pale")]
    _run(parse_scene(model, _png(), previous=previous))
    assert "character.face" in model.calls[0]["user_text"]


@pytest.mark.parametrize(
    ("reply", "fragment"),
    [
        ({}, "non-empty"),
        ({"entities": [{"id": "Bad Id", "name": "x"}]}, "'Bad Id'"),
        ({"entities": [{"id": "sky", "name": "Sky", "bbox": [0.9, 0.0, 0.5, 0.5]}]}, "'sky'"),
        ({"entities": [{"id": "sky", "name": "Sky"}, {"id": "sky", "name": "Sky"}]}, "duplicate"),
    ],
)
def test_entities_from_reply_errors_are_locatable(reply: dict[str, Any], fragment: str) -> None:
    with pytest.raises(SceneParseError) as exc_info:
        entities_from_reply(reply)
    assert fragment in str(exc_info.value)


def test_parse_intent_drops_unknown_targets() -> None:
    entities = [
        SceneEntity(id="environment.sky", name="Sky"),
        SceneEntity(id="character.face", name="Face", status=EntityStatus.LOCKED),
    ]
    model = FakeModel(
        {
            "operation": "replace",
            "target_entity_ids": ["environment.sky", "environment.ghost"],
            "location_hint": "upper half",
            "change_description": "Turn the sky into a Halloween night with a full moon.",
        }
    )
    intent = _run(parse_intent(model, "把天空改成万圣节夜晚", entities))
    assert intent.operation == EditOperation.REPLACE
    assert intent.target_entity_ids == ["environment.sky"]
    assert '"status": "locked"' in model.calls[0]["user_text"]


def _settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        openai_api_key="sk-test",
        openai_base_url="https://api.openai.com/v1",
        provider_allowed_hosts=["api.openai.com"],
    )


def test_vision_client_sends_images_and_parses_json() -> None:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "choices": [{"message": {"content": json.dumps({"ok": True})}}]
    }
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post = AsyncMock(return_value=response)

    vision = VisionClient(config=_settings(), client=client)
    result = _run(vision.complete_json(system_prompt="s", user_text="u", images=[_png()]))

    assert result == {"ok": True}
    payload = client.post.await_args.kwargs["json"]
    assert payload["model"] == "gpt-4o"
    assert payload["response_format"] == {"type": "json_object"}
    parts = payload["messages"][1]["content"]
    assert parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_vision_client_targets_custom_endpoint_and_strips_code_fence() -> None:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "choices": [{"message": {"content": '```json\n{"entities": []}\n```'}}]
    }
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post = AsyncMock(return_value=response)
    config = Settings(  # type: ignore[call-arg]
        openai_api_key="sk-test",
        provider_allowed_hosts=["api.openai.com", "dashscope.aliyuncs.com"],
    )
    vision = VisionClient(
        config=config,
        client=client,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key="ds-key",
        model="qwen3-vl-plus",
    )

    assert _run(vision.complete_json(system_prompt="s", user_text="u")) == {"entities": []}
    call = client.post.await_args
    assert call.args[0] == "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    assert call.kwargs["headers"]["Authorization"] == "Bearer ds-key"
    assert call.kwargs["json"]["model"] == "qwen3-vl-plus"
    assert vision.model == "qwen3-vl-plus"


def test_vision_client_rejects_missing_key_and_unlisted_host() -> None:
    config = Settings(  # type: ignore[call-arg]
        openai_api_key="sk-test", provider_allowed_hosts=["api.openai.com"]
    )
    with pytest.raises(VisionError):
        VisionClient(config=config, api_key="  ", model="qwen3-vl-plus")
    with pytest.raises(ValueError):
        VisionClient(config=config, base_url="https://evil.example.com/v1", api_key="k")


@pytest.mark.parametrize(
    ("provider", "dashscope_key", "expected_model"),
    [
        ("dashscope", "ds-key", "qwen3-vl-plus"),
        ("dashscope", "", "gpt-4o"),
        ("openai", "ds-key", "gpt-4o"),
    ],
)
def test_scene_client_uses_dedicated_model_only_when_configured(
    provider: str, dashscope_key: str, expected_model: str
) -> None:
    config = Settings(  # type: ignore[call-arg]
        openai_api_key="sk-test",
        dashscope_api_key=dashscope_key,
        cedit_scene_provider=provider,
        provider_allowed_hosts=["api.openai.com", "dashscope.aliyuncs.com"],
    )
    assert scene_model_name(config) == expected_model
    assert scene_vision_client(config).model == expected_model


def test_dashscope_key_accepts_alibaba_env_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INFD_DASHSCOPE_API_KEY", raising=False)
    monkeypatch.setenv("INFD_ALIBABA_API_KEY", "ali-key")
    assert Settings(_env_file=None).dashscope_api_key == "ali-key"  # type: ignore[call-arg]


def test_vision_client_rejects_non_object_json() -> None:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"choices": [{"message": {"content": "[1, 2]"}}]}
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post = AsyncMock(return_value=response)
    vision = VisionClient(config=_settings(), client=client)
    with pytest.raises(VisionError):
        _run(vision.complete_json(system_prompt="s", user_text="u"))
