"""Tests for txt2img backend routing."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.pipeline.comfyui_client import ComfyUIClient
from app.pipeline.txt2img_router import (
    build_txt2img_workflow_for_backend,
    resolve_txt2img_backend,
)
from app.system.schemas import (
    CapabilitiesResponse,
    FeatureCapability,
    GpuInfo,
    ModelsCapability,
    ServiceStatus,
)


def _caps(backend: str, enabled: bool = True) -> CapabilitiesResponse:
    return CapabilitiesResponse(
        tier="local_8gb",
        gpu=GpuInfo(available=True, vram_total_mb=8192),
        services={
            "ollama": ServiceStatus(ok=True, url="http://127.0.0.1:11434/v1"),
            "comfyui": ServiceStatus(ok=True, url="http://127.0.0.1:8188"),
        },
        models=ModelsCapability(sd15_txt2img=True),
        features={
            "txt2img": FeatureCapability(
                enabled=enabled,
                backend=backend,
                available_backends=[backend] if enabled else [],
            ),
        },
    )


async def _resolve_auto() -> str:
    return await resolve_txt2img_backend("auto")


async def _resolve_disabled() -> None:
    await resolve_txt2img_backend("auto")


def test_resolve_auto_returns_detected_backend() -> None:
    with patch(
        "app.pipeline.txt2img_router.gather_capabilities",
        new=AsyncMock(return_value=_caps("sd15")),
    ):
        assert asyncio_run(_resolve_auto()) == "sd15"


def test_resolve_raises_when_txt2img_disabled() -> None:
    with patch(
        "app.pipeline.txt2img_router.gather_capabilities",
        new=AsyncMock(return_value=_caps("sd15", enabled=False)),
    ):
        with pytest.raises(HTTPException) as exc_info:
            asyncio_run(_resolve_disabled())
        assert exc_info.value.status_code == 503


def test_build_workflow_sd15() -> None:
    client = ComfyUIClient()
    workflow = asyncio_run(
        build_txt2img_workflow_for_backend(
            client,
            "sd15",
            prompt="a cat",
            negative_prompt="ugly",
            seed=1,
            steps=20,
        )
    )
    assert workflow["2"]["inputs"]["text"] == "a cat"


def asyncio_run(coro):  # type: ignore[no-untyped-def]
    import asyncio

    return asyncio.run(coro)
