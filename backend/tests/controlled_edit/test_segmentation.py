"""Prompt validation and independent segmentation-service contract tests."""

import base64
import io
import json

import httpx
import pytest
from PIL import Image
from pydantic import ValidationError

from app.config import settings
from app.controlled_edit.sam3_client import segment_sam3
from app.controlled_edit.segmentation import (
    SegmentationUnavailableError,
    SegmentRequest,
)


def test_point_prompts_require_matching_labels_and_source_coordinates() -> None:
    """Invalid prompts fail before loading a segmentation model."""
    for payload in [
        {},
        {"points": [[0.5, 0.5]]},
        {"points": [[1.1, 0.5]], "labels": [1]},
        {"provider": "sam2", "text": "shield"},
    ]:
        with pytest.raises(ValidationError):
            SegmentRequest.model_validate(payload)
    assert SegmentRequest(points=[(0.5, 0.5)], labels=[1]).provider == "sam2"


@pytest.mark.asyncio
async def test_sam3_http_contract_and_missing_configuration(monkeypatch) -> None:
    """The optional service receives source bytes and returns source-resolution PNGs."""
    prompt = SegmentRequest(provider="sam3", text="shield")
    with pytest.raises(SegmentationUnavailableError):
        await segment_sam3(
            b"source", prompt, settings.model_copy(update={"cedit_sam3_base_url": ""})
        )
    buffer = io.BytesIO()
    Image.new("L", (31, 19), 255).save(buffer, format="PNG")
    mask = buffer.getvalue()

    def reply(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/segment"
        body = json.loads(request.content)
        assert base64.b64decode(body["image_base64"]) == b"source"
        assert body["prompt"]["text"] == "shield"
        return httpx.Response(
            200,
            json={
                "masks": [
                    {
                        "png_base64": base64.b64encode(mask).decode(),
                        "score": 0.91,
                    }
                ]
            },
        )

    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: client_type(transport=httpx.MockTransport(reply), **kw)
    )
    config = settings.model_copy(update={"cedit_sam3_base_url": "http://127.0.0.1:8123"})
    assert await segment_sam3(b"source", prompt, config) == [(mask, 0.91)]
