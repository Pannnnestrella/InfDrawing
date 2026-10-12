"""Unit tests for Wan 2.7 multimodal edit request shaping."""

from __future__ import annotations

import asyncio
import base64
import json

import httpx

from app.config import Settings
from app.controlled_edit.region_ops import target_pixel_bboxes
from app.controlled_edit.schemas import BBox, BBoxSource, EntityStatus, SceneEntity
from app.pipeline.image_providers.dashscope_wan27_edit import DashScopeWan27EditProvider


def _png() -> bytes:
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )


def test_wan27_multi_image_edit_sends_bbox_list() -> None:
    captured: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/generation"):
            captured["body"] = request.content
            return httpx.Response(
                200,
                json={
                    "output": {
                        "choices": [
                            {
                                "message": {
                                    "content": [{"image": "https://example.com/out.png"}]
                                }
                            }
                        ]
                    }
                },
            )
        if request.url.host == "example.com":
            return httpx.Response(200, content=_png())
        return httpx.Response(404)

    async def scenario() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            config = Settings(
                dashscope_api_key="sk-test",
                dashscope_base_url="https://dashscope.aliyuncs.com/api/v1",
                cloud_image_timeout_seconds=30.0,
            )
            provider = DashScopeWan27EditProvider(
                config, client=client, model="wan2.7-image-pro"
            )
            result = await provider.multi_image_edit(
                image_bytes=_png(),
                reference_images=[],
                prompt="改成短刀",
                size="2K",
                bbox_list=[[[10, 20, 30, 40]]],
            )
            assert result == _png()

    asyncio.run(scenario())
    body = json.loads(captured["body"])
    assert body["model"] == "wan2.7-image-pro"
    assert body["parameters"]["bbox_list"] == [[[10, 20, 30, 40]]]
    assert body["parameters"]["size"] == "2K"
    content = body["input"]["messages"][0]["content"]
    assert len([item for item in content if "image" in item]) == 1
    assert content[-1]["text"].startswith("改成短刀")


def test_target_pixel_bboxes_picks_largest() -> None:
    entities = [
        SceneEntity(
            id="character.sword",
            name="Sword",
            bbox=BBox(x=0.1, y=0.1, w=0.1, h=0.2),
            bbox_source=BBoxSource.MODEL,
            status=EntityStatus.EDITABLE,
        ),
        SceneEntity(
            id="character.shield",
            name="Shield",
            bbox=BBox(x=0.5, y=0.4, w=0.2, h=0.2),
            bbox_source=BBoxSource.MODEL,
            status=EntityStatus.EDITABLE,
        ),
    ]
    boxes = target_pixel_bboxes(
        (1000, 1000), entities, ["character.sword", "character.shield"], max_boxes=1
    )
    assert len(boxes) == 1
    assert boxes[0][0] >= 500
