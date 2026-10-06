"""Tests for capability probing and tier inference."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.system.capabilities import (
    build_features,
    infer_tier,
    probe_gpu,
)
from app.system.schemas import GpuInfo, ModelsCapability, ServiceStatus


def test_probe_gpu_unavailable_when_nvidia_smi_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_not_found(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError("nvidia-smi")

    monkeypatch.setattr("app.system.capabilities.subprocess.run", raise_not_found)
    assert probe_gpu().available is False


def test_infer_tier_local_8gb() -> None:
    gpu = GpuInfo(available=True, name="RTX 4060", vram_total_mb=8192, vram_free_mb=6000)
    comfyui = ServiceStatus(ok=True, url="http://127.0.0.1:8188")
    models = ModelsCapability(sd15_txt2img=True, sd15_inpaint=True)
    assert infer_tier(gpu, comfyui, models, dashscope_configured=False) == "local_8gb"


def test_infer_tier_cpu_only_without_comfyui() -> None:
    gpu = GpuInfo(available=True, vram_total_mb=8192, vram_free_mb=6000)
    comfyui = ServiceStatus(ok=False, url="http://127.0.0.1:8188")
    models = ModelsCapability()
    assert infer_tier(gpu, comfyui, models, dashscope_configured=False) == "cpu_only"


def test_infer_tier_api_fallback_with_openai() -> None:
    gpu = GpuInfo(available=False)
    comfyui = ServiceStatus(ok=False, url="http://127.0.0.1:8188")
    models = ModelsCapability()
    assert (
        infer_tier(
            gpu,
            comfyui,
            models,
            dashscope_configured=False,
            openai_configured=True,
        )
        == "api_fallback"
    )


def test_build_features_enables_sd15_on_local_tier() -> None:
    comfyui = ServiceStatus(ok=True, url="http://127.0.0.1:8188")
    models = ModelsCapability(sd15_txt2img=True, sd15_inpaint=True)
    with patch("app.system.capabilities.rembg_available", return_value=False):
        features = build_features("local_8gb", comfyui, models, dashscope_configured=False)
    assert features["txt2img"].enabled is True
    assert features["txt2img"].backend == "sd15"
    assert features["txt2img"].available_backends == ["sd15"]
    assert features["inpaint"].enabled is True
    assert features["decompose"].enabled is False


def test_build_features_includes_cloud_backends() -> None:
    comfyui = ServiceStatus(ok=False, url="http://127.0.0.1:8188")
    models = ModelsCapability()
    features = build_features(
        "api_fallback",
        comfyui,
        models,
        dashscope_configured=True,
        openai_configured=True,
    )
    assert features["txt2img"].enabled is True
    assert features["txt2img"].available_backends == ["openai", "dashscope"]
    assert features["inpaint"].available_backends == ["openai", "dashscope"]
    assert features["decompose"].enabled is True
    assert features["decompose"].backend == "dashscope_seg"


def test_build_features_enables_decompose_with_rembg() -> None:
    comfyui = ServiceStatus(ok=True, url="http://127.0.0.1:8188")
    models = ModelsCapability(sd15_inpaint=True)
    with patch("app.system.capabilities.rembg_available", return_value=True):
        features = build_features("local_8gb", comfyui, models, dashscope_configured=False)
    assert features["decompose"].enabled is True
    assert features["decompose"].backend == "rembg_sd15"


def test_build_features_enables_text_edit_with_easyocr() -> None:
    comfyui = ServiceStatus(ok=True, url="http://127.0.0.1:8188")
    models = ModelsCapability(sd15_inpaint=True)
    with patch("app.system.capabilities.easyocr_available", return_value=True):
        features = build_features("local_8gb", comfyui, models, dashscope_configured=False)
    assert features["text_edit"].enabled is True
    assert features["text_edit"].backend == "ocr_inpaint_overlay"


def test_gather_capabilities_integration_mock() -> None:
    gpu = GpuInfo(available=True, name="RTX 4060", vram_total_mb=8192, vram_free_mb=6000)

    async def run() -> None:
        from app.system.capabilities import gather_capabilities

        caps = await gather_capabilities()
        assert caps.tier == "local_8gb"
        assert caps.models.sd15_txt2img is True
        assert caps.features["txt2img"].enabled is True

    with (
        patch("app.system.capabilities.probe_gpu", return_value=gpu),
        patch(
            "app.system.capabilities.probe_ollama",
            new=AsyncMock(return_value=ServiceStatus(ok=True, url="http://127.0.0.1:11434/v1")),
        ),
        patch(
            "app.system.capabilities.probe_comfyui",
            new=AsyncMock(return_value=ServiceStatus(ok=True, url="http://127.0.0.1:8188")),
        ),
        patch(
            "app.system.capabilities.probe_comfyui_models",
            new=AsyncMock(
                return_value=ModelsCapability(sd15_txt2img=True, sd15_inpaint=True),
            ),
        ),
    ):
        asyncio.run(run())
