"""Tests for prompt compilation, anchors, sizing, and the multi-image provider call."""

from __future__ import annotations

import asyncio
import base64
import io
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from PIL import Image

from app.config import Settings
from app.controlled_edit.anchors import ANCHOR_MIN_SIDE, crop_entity
from app.controlled_edit.prompt_compiler import compile_edit_prompt
from app.controlled_edit.schemas import (
    BBox,
    EditIntent,
    EditOperation,
    EntityStatus,
    SceneEntity,
)
from app.controlled_edit.sizing import (
    choose_size,
    pad_to_supported,
    restore_original_frame,
)
from app.pipeline.image_providers.dashscope_qwen_edit import DashScopeQwenEditProvider
from app.pipeline.image_providers.openai_images import OpenAIImageProvider


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def _png(width: int, height: int, color: tuple[int, int, int] = (10, 120, 200)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _size(data: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(data)) as image:
        return image.size


ENTITIES = [
    SceneEntity(
        id="character.face",
        name="Face",
        description="pale, green eyes",
        status=EntityStatus.LOCKED,
        anchor_artifact_id="a-face",
    ),
    SceneEntity(id="character.sword", name="Sword", status=EntityStatus.LOCKED),
    SceneEntity(
        id="character.shield",
        name="Shield",
        status=EntityStatus.LOCKED,
        anchor_artifact_id="a-shield",
    ),
    SceneEntity(id="character.costume", name="Costume", status=EntityStatus.APPROVED),
    SceneEntity(id="environment.sky", name="Sky"),
]


def test_prompt_lists_locks_with_reference_numbers() -> None:
    intent = EditIntent(
        operation=EditOperation.REPLACE,
        target_entity_ids=["environment.sky"],
        location_hint="background",
        change_description="Turn the sky into a Halloween night with purple fog.",
    )
    compiled = compile_edit_prompt(intent, ENTITIES)

    assert [e.id for e in compiled.reference_entities] == ["character.face", "character.shield"]
    prompt = compiled.prompt
    assert "Face (character.face) — pale, green eyes. Must match reference image 2." in prompt
    assert "Shield (character.shield). Must match reference image 3." in prompt
    assert "- Sword (character.sword)." in prompt
    assert "Keep unchanged unless" in prompt and "Costume" in prompt
    assert "Elements to change: Sky" in prompt
    assert "identity references only" in prompt


def test_prompt_excludes_targets_and_caps_references() -> None:
    intent = EditIntent(
        operation=EditOperation.RECOLOR,
        target_entity_ids=["character.costume"],
        change_description="Make the costume orange.",
    )
    compiled = compile_edit_prompt(
        intent, ENTITIES, max_references=1, retry_feedback="Face drifted."
    )
    assert "Keep unchanged unless" not in compiled.prompt
    assert len(compiled.reference_entities) == 1
    assert "reference image 3" not in compiled.prompt
    assert "previous attempt was rejected: Face drifted." in compiled.prompt


def test_prompt_without_locks_has_no_reference_note() -> None:
    intent = EditIntent(operation=EditOperation.ADD, change_description="Add a pumpkin.")
    compiled = compile_edit_prompt(intent, [SceneEntity(id="environment", name="Environment")])
    assert "Preserve exactly" not in compiled.prompt
    assert "identity references" not in compiled.prompt


def test_prompt_target_only_omits_preserve_lists() -> None:
    intent = EditIntent(
        operation=EditOperation.REPLACE,
        target_entity_ids=["environment.sky"],
        location_hint="background",
        change_description="Turn the sky into a Halloween night with purple fog.",
    )
    compiled = compile_edit_prompt(intent, ENTITIES, prompt_style="target_only")
    prompt = compiled.prompt
    assert [e.id for e in compiled.reference_entities] == ["character.face", "character.shield"]
    assert "Elements to change: Sky" in prompt
    assert "Preserve exactly" not in prompt
    assert "Keep unchanged unless" not in prompt
    assert "Sword (character.sword)" not in prompt
    assert "Costume" not in prompt
    assert "Reference image 2: Face (character.face)" in prompt
    assert "leave everything else as it already appears" in prompt
    assert "identity references only" in prompt


def test_crop_entity_pads_and_upscales() -> None:
    crop = crop_entity(_png(400, 200), BBox(x=0.5, y=0.5, w=0.1, h=0.1))
    assert min(_size(crop)) >= ANCHOR_MIN_SIDE


@pytest.mark.parametrize(
    ("width", "height", "expected"),
    [(1000, 1000, (1024, 1024)), (1920, 1080, (1536, 1024)), (800, 1400, (1024, 1536))],
)
def test_choose_size(width: int, height: int, expected: tuple[int, int]) -> None:
    assert choose_size(width, height) == expected


def test_pad_and_restore_round_trip_keeps_original_size() -> None:
    original = _png(1920, 1080)
    padded = pad_to_supported(original)
    assert padded.size == "1536x1024"
    pw, ph = _size(padded.png)
    assert pw / ph == pytest.approx(1.5, rel=0.01)

    generated = _png(1536, 1024, (0, 0, 0))
    restored = restore_original_frame(generated, padded)
    assert _size(restored) == (1920, 1080)


def _provider_settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        openai_api_key="sk-test",
        openai_base_url="https://api.openai.com/v1",
        provider_allowed_hosts=["api.openai.com"],
    )


def _ok_response() -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"data": [{"b64_json": base64.b64encode(b"out").decode()}]}
    return response


def test_multi_image_edit_sends_ordered_images_and_fidelity() -> None:
    client = AsyncMock(spec=httpx.AsyncClient)
    client.request = AsyncMock(return_value=_ok_response())
    provider = OpenAIImageProvider(config=_provider_settings(), client=client)

    result = _run(
        provider.multi_image_edit(
            image_bytes=b"main",
            reference_images=[b"ref-a", b"ref-b"],
            prompt="p",
            size="1536x1024",
            input_fidelity="high",
        )
    )
    assert result == b"out"
    kwargs = client.request.await_args.kwargs
    assert [f[1][1] for f in kwargs["files"]] == [b"main", b"ref-a", b"ref-b"]
    assert kwargs["data"]["size"] == "1536x1024"
    assert kwargs["data"]["input_fidelity"] == "high"


def test_prompt_primary_last_numbers_references_from_one() -> None:
    intent = EditIntent(
        operation=EditOperation.REPLACE,
        target_entity_ids=["environment.sky"],
        change_description="night sky",
    )
    compiled = compile_edit_prompt(intent, ENTITIES, image_layout="primary_last")
    assert "Edit the last image (image 3)" in compiled.prompt
    assert "Must match reference image 1." in compiled.prompt
    assert "Images before the last one are identity references" in compiled.prompt


def test_qwen_edit_sends_references_then_primary() -> None:
    config = Settings(  # type: ignore[call-arg]
        dashscope_api_key="sk-ali",
        dashscope_base_url="https://dashscope.aliyuncs.com/api/v1",
        provider_allowed_hosts=["dashscope.aliyuncs.com"],
        cedit_image_model="qwen-image-edit-plus",
    )
    client = AsyncMock(spec=httpx.AsyncClient)
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "output": {"choices": [{"message": {"content": [{"image": "https://cdn.example/a.png"}]}}]}
    }
    download = MagicMock()
    download.status_code = 200
    download.content = b"png-bytes"
    download.raise_for_status = MagicMock()
    client.request = AsyncMock(return_value=response)
    client.get = AsyncMock(return_value=download)
    provider = DashScopeQwenEditProvider(config=config, client=client)
    result = _run(
        provider.multi_image_edit(
            image_bytes=b"main",
            reference_images=[b"ref-a", b"ref-b", b"ref-c"],
            prompt="edit",
            size="1024x1024",
        )
    )
    assert result == b"png-bytes"
    payload = client.request.await_args.kwargs["json"]
    content = payload["input"]["messages"][0]["content"]
    assert payload["parameters"]["size"] == "1024*1024"
    assert len([item for item in content if "image" in item]) == 3
    assert content[-2]["image"].startswith("data:image/png;base64,")
    assert content[-1] == {"text": "edit"}


def test_multi_image_edit_retries_without_unsupported_fidelity() -> None:
    rejected = MagicMock()
    rejected.status_code = 400
    rejected.json.return_value = {"error": {"message": "Unknown parameter: 'input_fidelity'."}}
    client = AsyncMock(spec=httpx.AsyncClient)
    client.request = AsyncMock(side_effect=[rejected, _ok_response()])
    provider = OpenAIImageProvider(config=_provider_settings(), client=client)

    result = _run(
        provider.multi_image_edit(
            image_bytes=b"main", reference_images=[], prompt="p", input_fidelity="high"
        )
    )
    assert result == b"out"
    assert "input_fidelity" not in client.request.await_args_list[1].kwargs["data"]
