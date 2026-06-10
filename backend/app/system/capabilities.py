"""Probe GPU, ComfyUI, Ollama and derive feature flags."""

from __future__ import annotations

import subprocess
from typing import Any

import httpx

from app.config import settings
from app.pipeline.decompose import rembg_available
from app.pipeline.text_detect import easyocr_available
from app.system.schemas import (
    CapabilitiesResponse,
    FeatureCapability,
    GpuInfo,
    ModelsCapability,
    ServiceStatus,
)

LOCAL_COMFYUI_HOSTS = {"127.0.0.1", "localhost"}


def _is_remote_comfyui_url(url: str) -> bool:
    lowered = url.lower()
    return not any(host in lowered for host in LOCAL_COMFYUI_HOSTS)


def probe_gpu() -> GpuInfo:
    """Read GPU info via nvidia-smi when available."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return GpuInfo(available=False)
        line = result.stdout.strip().splitlines()[0]
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 3:
            return GpuInfo(available=False)
        name = parts[0]
        total_mb = int(float(parts[1]))
        free_mb = int(float(parts[2]))
        return GpuInfo(
            available=True,
            name=name,
            vram_total_mb=total_mb,
            vram_free_mb=free_mb,
        )
    except (FileNotFoundError, OSError, ValueError, subprocess.SubprocessError):
        return GpuInfo(available=False)


async def probe_ollama() -> ServiceStatus:
    """Check Ollama OpenAI-compatible API."""
    url = settings.ollama_base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url.replace('/v1', '')}/api/tags")
            response.raise_for_status()
        return ServiceStatus(ok=True, url=url, remote=False)
    except httpx.HTTPError:
        return ServiceStatus(ok=False, url=url, remote=False)


async def probe_comfyui() -> ServiceStatus:
    """Check ComfyUI HTTP API."""
    url = settings.comfyui_base_url.rstrip("/")
    remote = _is_remote_comfyui_url(url)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/system_stats")
            response.raise_for_status()
        return ServiceStatus(ok=True, url=url, remote=remote)
    except httpx.HTTPError:
        return ServiceStatus(ok=False, url=url, remote=remote)


def _extract_checkpoint_names(object_info: dict[str, Any]) -> list[str]:
    loader = object_info.get("CheckpointLoaderSimple") or object_info.get(
        "CheckpointLoader"
    )
    if not isinstance(loader, dict):
        return []
    required = loader.get("input", {}).get("required", {})
    ckpt_field = required.get("ckpt_name")
    if not ckpt_field or not isinstance(ckpt_field, (list, tuple)):
        return []
    names = ckpt_field[0]
    if not isinstance(names, list):
        return []
    return [str(name).lower() for name in names]


def _match_any(names: list[str], tokens: tuple[str, ...]) -> bool:
    return any(any(token in name for token in tokens) for name in names)


async def probe_comfyui_models(comfyui_ok: bool) -> ModelsCapability:
    """Inspect ComfyUI object_info for installed checkpoints."""
    if not comfyui_ok:
        return ModelsCapability()

    url = settings.comfyui_base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{url}/object_info")
            response.raise_for_status()
            object_info = response.json()
    except httpx.HTTPError:
        return ModelsCapability()

    checkpoints = _extract_checkpoint_names(object_info)
    node_names = {key.lower() for key in object_info}

    sd15_inpaint = any("inpaint" in name for name in checkpoints)
    sd15_txt2img = any(
        any(token in name for token in ("v1-5", "v1_5", "sd1.5", "sd-v1-5", "sd_v1_5"))
        and "inpaint" not in name
        for name in checkpoints
    )

    flux_txt2img = _match_any(checkpoints, ("flux",))
    flux_fill = _match_any(checkpoints, ("flux", "fill"))
    sam2_segment = any("sam" in node for node in node_names)
    anytext2 = any("anytext" in node for node in node_names)

    return ModelsCapability(
        sd15_txt2img=sd15_txt2img,
        sd15_inpaint=sd15_inpaint,
        flux_txt2img=flux_txt2img,
        sam2_segment=sam2_segment,
        flux_fill=flux_fill,
        anytext2=anytext2,
    )


def infer_tier(
    gpu: GpuInfo,
    comfyui: ServiceStatus,
    models: ModelsCapability,
    *,
    dashscope_configured: bool,
) -> str:
    """Map hardware + services to a coarse capability tier."""
    if dashscope_configured and not comfyui.ok:
        return "api_fallback"
    if not comfyui.ok:
        return "cpu_only"
    if not gpu.available:
        return "cpu_only"

    vram = gpu.vram_total_mb or 0
    if vram >= 40_000:
        return "gpu_48gb"
    if vram >= 20_000:
        return "gpu_24gb"
    if vram > 0:
        return "local_8gb"
    return "cpu_only"


def build_features(
    tier: str,
    comfyui: ServiceStatus,
    models: ModelsCapability,
    *,
    dashscope_configured: bool,
) -> dict[str, FeatureCapability]:
    """Derive user-facing feature flags from tier and models."""
    txt2img_backend: str | None = None
    if models.flux_txt2img and tier in {"gpu_24gb", "gpu_48gb"}:
        txt2img_backend = "flux"
    elif models.sd15_txt2img:
        txt2img_backend = "sd15"
    elif dashscope_configured:
        txt2img_backend = "dashscope_api"

    inpaint_backend: str | None = None
    if models.flux_fill and tier in {"gpu_24gb", "gpu_48gb"}:
        inpaint_backend = "flux_fill"
    elif models.sd15_inpaint:
        inpaint_backend = "sd15"

    txt2img_enabled = comfyui.ok and txt2img_backend is not None
    inpaint_enabled = comfyui.ok and inpaint_backend is not None

    decompose_sam = (
        comfyui.ok
        and models.flux_txt2img
        and models.sam2_segment
        and tier in {"gpu_24gb", "gpu_48gb"}
    )
    decompose_local = comfyui.ok and models.sd15_inpaint and rembg_available()
    decompose_enabled = decompose_sam or decompose_local
    decompose_backend = (
        "flux_sam"
        if decompose_sam
        else "rembg_sd15"
        if decompose_local
        else None
    )

    text_edit_local = comfyui.ok and models.sd15_inpaint and easyocr_available()
    text_edit_anytext = (
        comfyui.ok and models.anytext2 and tier in {"gpu_24gb", "gpu_48gb"}
    )
    text_edit_enabled = text_edit_local or text_edit_anytext
    text_edit_backend = (
        "anytext2"
        if text_edit_anytext
        else "ocr_inpaint_overlay"
        if text_edit_local
        else None
    )

    features: dict[str, FeatureCapability] = {
        "txt2img": FeatureCapability(
            enabled=txt2img_enabled,
            backend=txt2img_backend,
            reason=None
            if txt2img_enabled
            else _txt2img_reason(comfyui, txt2img_backend, dashscope_configured),
        ),
        "inpaint": FeatureCapability(
            enabled=inpaint_enabled,
            backend=inpaint_backend,
            reason=None
            if inpaint_enabled
            else _inpaint_reason(comfyui, inpaint_backend),
        ),
        "plugin_t2i": FeatureCapability(
            enabled=txt2img_enabled,
            backend=txt2img_backend,
            reason=None if txt2img_enabled else "依赖 txt2img 能力",
        ),
        "decompose": FeatureCapability(
            enabled=decompose_enabled,
            backend=decompose_backend,
            reason=None
            if decompose_enabled
            else _decompose_reason(comfyui, models, tier),
        ),
        "tab_inpaint": FeatureCapability(
            enabled=inpaint_enabled,
            backend=inpaint_backend,
            reason=None if inpaint_enabled else "依赖 inpaint 能力",
        ),
        "text_edit": FeatureCapability(
            enabled=text_edit_enabled,
            backend=text_edit_backend,
            reason=None
            if text_edit_enabled
            else _text_edit_reason(comfyui, models),
        ),
    }
    return features


def _txt2img_reason(
    comfyui: ServiceStatus,
    backend: str | None,
    dashscope_configured: bool,
) -> str:
    if not comfyui.ok:
        return f"ComfyUI 不可达（{comfyui.url}）"
    if backend is None:
        if dashscope_configured:
            return "未检测到本地生图模型，可配置 DashScope fallback"
        return "未安装 SD1.5 或 Flux checkpoint"
    return "生图能力不可用"


def _inpaint_reason(comfyui: ServiceStatus, backend: str | None) -> str:
    if not comfyui.ok:
        return f"ComfyUI 不可达（{comfyui.url}）"
    if backend is None:
        return "未安装 SD1.5 inpaint 或 Flux Fill 模型"
    return "inpaint 不可用"


def _decompose_reason(comfyui: ServiceStatus, models: ModelsCapability, tier: str) -> str:
    if not comfyui.ok:
        return f"ComfyUI 不可达（{comfyui.url}）"
    if not rembg_available():
        return "缺少 rembg 依赖（pip install rembg onnxruntime）"
    if not models.sd15_inpaint:
        return "未安装 SD1.5 inpaint 模型"
    if tier in {"gpu_24gb", "gpu_48gb"} and not models.sam2_segment:
        return "本机可用 rembg 双图层；多元素拆解需 SAM2 节点"
    return "元素拆解不可用"


def _text_edit_reason(comfyui: ServiceStatus, models: ModelsCapability) -> str:
    if not comfyui.ok:
        return f"ComfyUI 不可达（{comfyui.url}）"
    if not easyocr_available():
        return "缺少 easyocr 依赖（pip install easyocr）"
    if not models.sd15_inpaint:
        return "未安装 SD1.5 inpaint 模型"
    return "文字编辑不可用"


async def gather_capabilities() -> CapabilitiesResponse:
    """Collect a full capability snapshot for API and CLI."""
    gpu = probe_gpu()
    ollama = await probe_ollama()
    comfyui = await probe_comfyui()
    models = await probe_comfyui_models(comfyui.ok)
    dashscope_configured = bool(settings.dashscope_api_key.strip())

    tier = infer_tier(
        gpu,
        comfyui,
        models,
        dashscope_configured=dashscope_configured,
    )
    features = build_features(
        tier,
        comfyui,
        models,
        dashscope_configured=dashscope_configured,
    )

    return CapabilitiesResponse(
        tier=tier,
        gpu=gpu,
        services={
            "ollama": ollama,
            "comfyui": comfyui,
        },
        models=models,
        features=features,
    )
