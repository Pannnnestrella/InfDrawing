"""Tests for cloud image providers and backend resolution."""

from __future__ import annotations

import asyncio
import base64
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException

from app.config import Settings
from app.pipeline.image_providers.dashscope_wanx import DashScopeWanxProvider
from app.pipeline.image_providers.openai_images import OpenAIImageProvider
from app.pipeline.txt2img_router import resolve_image_backend
from app.system.schemas import (
    CapabilitiesResponse,
    FeatureCapability,
    GpuInfo,
    ModelsCapability,
    ServiceStatus,
)


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def _settings(**overrides: object) -> Settings:
    base = {
        "openai_api_key": "sk-test",
        "openai_base_url": "https://api.openai.com/v1",
        "dashscope_api_key": "ds-test",
        "dashscope_base_url": "https://dashscope.aliyuncs.com/api/v1",
        "provider_allowed_hosts": [
            "api.openai.com",
            "dashscope.aliyuncs.com",
            "127.0.0.1",
            "localhost",
        ],
        "cloud_image_timeout_seconds": 5.0,
        "cloud_image_poll_seconds": 0.01,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _caps(available: list[str], *, enabled: bool = True) -> CapabilitiesResponse:
    preferred = available[0] if available else None
    return CapabilitiesResponse(
        tier="local_8gb",
        gpu=GpuInfo(available=True, vram_total_mb=8192),
        services={
            "ollama": ServiceStatus(ok=True, url="http://127.0.0.1:11434/v1"),
            "comfyui": ServiceStatus(ok=True, url="http://127.0.0.1:8188"),
        },
        models=ModelsCapability(sd15_txt2img=True, sd15_inpaint=True),
        features={
            "txt2img": FeatureCapability(
                enabled=enabled,
                backend=preferred,
                available_backends=available,
            ),
            "inpaint": FeatureCapability(
                enabled=enabled,
                backend=preferred,
                available_backends=available,
            ),
        },
    )


def test_resolve_auto_prefers_local_then_cloud() -> None:
    with patch(
        "app.pipeline.txt2img_router.gather_capabilities",
        new=AsyncMock(return_value=_caps(["sd15", "openai", "dashscope"])),
    ):
        assert _run(resolve_image_backend("auto", feature="txt2img")) == "sd15"


def test_resolve_auto_falls_back_to_openai() -> None:
    with patch(
        "app.pipeline.txt2img_router.gather_capabilities",
        new=AsyncMock(return_value=_caps(["openai", "dashscope"])),
    ):
        assert _run(resolve_image_backend("auto", feature="txt2img")) == "openai"


def test_resolve_local_requires_comfy_backend() -> None:
    with patch(
        "app.pipeline.txt2img_router.gather_capabilities",
        new=AsyncMock(return_value=_caps(["openai"])),
    ):
        with pytest.raises(HTTPException) as exc_info:
            _run(resolve_image_backend("local", feature="txt2img"))
        assert exc_info.value.status_code == 503


def test_resolve_explicit_cloud_backend() -> None:
    with patch(
        "app.pipeline.txt2img_router.gather_capabilities",
        new=AsyncMock(return_value=_caps(["sd15", "dashscope"])),
    ):
        assert _run(resolve_image_backend("dashscope", feature="inpaint")) == "dashscope"


def test_openai_txt2img_decodes_b64() -> None:
    png = b"\x89PNG\r\n\x1a\nfake"
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "data": [{"b64_json": base64.b64encode(png).decode("ascii")}],
    }

    client = AsyncMock(spec=httpx.AsyncClient)
    client.request = AsyncMock(return_value=response)
    client.aclose = AsyncMock()

    provider = OpenAIImageProvider(config=_settings(), client=client)
    result = _run(provider.txt2img(prompt="a cat"))
    assert result == png
    client.request.assert_awaited()


def test_dashscope_txt2img_polls_and_downloads() -> None:
    submit = MagicMock()
    submit.status_code = 200
    submit.json.return_value = {"output": {"task_id": "task-1"}}

    poll = MagicMock()
    poll.status_code = 200
    poll.json.return_value = {
        "output": {
            "task_status": "SUCCEEDED",
            "results": [{"url": "https://example.com/out.png"}],
        }
    }

    download = MagicMock()
    download.status_code = 200
    download.content = b"cloud-bytes"
    download.raise_for_status = MagicMock()

    client = AsyncMock(spec=httpx.AsyncClient)
    client.request = AsyncMock(side_effect=[submit, poll])
    client.get = AsyncMock(return_value=download)
    client.aclose = AsyncMock()

    provider = DashScopeWanxProvider(config=_settings(), client=client)
    result = _run(provider.txt2img(prompt="a cabin", seed=7))
    assert result == b"cloud-bytes"


def test_dashscope_inpaint_sends_mask_function_and_data_urls() -> None:
    import io

    from PIL import Image

    def _tiny_png(color: tuple[int, int, int]) -> bytes:
        buffer = io.BytesIO()
        Image.new("RGB", (8, 8), color).save(buffer, format="PNG")
        return buffer.getvalue()

    submit = MagicMock()
    submit.status_code = 200
    submit.json.return_value = {"output": {"task_id": "task-mask"}}
    poll = MagicMock()
    poll.status_code = 200
    poll.json.return_value = {
        "output": {
            "task_status": "SUCCEEDED",
            "results": [{"url": "https://example.com/inpaint.png"}],
        }
    }
    download = MagicMock()
    download.status_code = 200
    download.content = b"inpaint-bytes"
    download.raise_for_status = MagicMock()

    client = AsyncMock(spec=httpx.AsyncClient)
    client.request = AsyncMock(side_effect=[submit, poll])
    client.get = AsyncMock(return_value=download)
    client.aclose = AsyncMock()

    provider = DashScopeWanxProvider(config=_settings(), client=client)
    result = _run(
        provider.inpaint(
            image_bytes=_tiny_png((10, 20, 30)),
            mask_bytes=_tiny_png((255, 255, 255)),
            prompt="replace the sky",
            seed=3,
        )
    )
    assert result == b"inpaint-bytes"
    body = client.request.await_args_list[0].kwargs["json"]
    assert body["model"] == "wanx2.1-imageedit"
    assert body["input"]["function"] == "description_edit_with_mask"
    assert body["input"]["base_image_url"].startswith("data:image/png;base64,")
    assert body["input"]["mask_image_url"].startswith("data:image/png;base64,")
    assert client.request.await_args_list[0].args[1].endswith(
        "/services/aigc/image2image/image-synthesis"
    )
