"""Tests for OpenAI instruction image_edit (maskless)."""

from __future__ import annotations

import asyncio
import base64
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.config import Settings
from app.pipeline.image_providers.openai_images import OpenAIImageProvider
from app.system.capabilities import build_features
from app.system.schemas import ModelsCapability, ServiceStatus


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def _settings(**overrides: object) -> Settings:
    base = {
        "openai_api_key": "sk-test",
        "openai_base_url": "https://api.openai.com/v1",
        "openai_image_model": "gpt-image-1",
        "provider_allowed_hosts": ["api.openai.com", "127.0.0.1", "localhost"],
        "cloud_image_timeout_seconds": 5.0,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_build_features_image_edit_requires_openai() -> None:
    comfyui = ServiceStatus(ok=True, url="http://127.0.0.1:8188")
    models = ModelsCapability(sd15_txt2img=True, sd15_inpaint=True)
    disabled = build_features(
        "local_8gb",
        comfyui,
        models,
        dashscope_configured=False,
        openai_configured=False,
    )
    assert disabled["image_edit"].enabled is False

    enabled = build_features(
        "local_8gb",
        comfyui,
        models,
        dashscope_configured=False,
        openai_configured=True,
    )
    assert enabled["image_edit"].enabled is True
    assert enabled["image_edit"].backend == "openai"


def test_openai_image_edit_omits_mask() -> None:
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
    result = _run(
        provider.image_edit(
            image_bytes=b"img",
            prompt="make the sky blue",
        )
    )
    assert result == png
    kwargs = client.request.await_args.kwargs
    assert "mask" not in kwargs.get("files", {})
