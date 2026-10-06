"""Probe GPU, ComfyUI, Ollama and derive feature flags."""

from __future__ import annotations

import subprocess
from typing import Any

import httpx

from app.config import settings
from app.controlled_edit.vision import scene_model_name, uses_dedicated_scene_model
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


async def probe_deepseek() -> ServiceStatus:
    """Check DeepSeek API reachability when a key is configured."""
    url = settings.deepseek_base_url.rstrip("/")
    if not settings.deepseek_api_key.strip():
        return ServiceStatus(ok=False, url=url, remote=True)
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(
                f"{url}/models",
                headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
            )
            response.raise_for_status()
        return ServiceStatus(ok=True, url=url, remote=True)
    except httpx.HTTPError:
        return ServiceStatus(ok=False, url=url, remote=True)


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
    openai_configured: bool = False,
) -> str:
    """Map hardware + services to a coarse capability tier."""
    if (dashscope_configured or openai_configured) and not comfyui.ok:
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
    openai_configured: bool = False,
) -> dict[str, FeatureCapability]:
    """Derive user-facing feature flags from tier, models, and cloud keys."""
    local_txt2img: list[str] = []
    if comfyui.ok and models.flux_txt2img and tier in {"gpu_24gb", "gpu_48gb"}:
        local_txt2img.append("flux")
    if comfyui.ok and models.sd15_txt2img:
        local_txt2img.append("sd15")

    local_inpaint: list[str] = []
    if comfyui.ok and models.flux_fill and tier in {"gpu_24gb", "gpu_48gb"}:
        local_inpaint.append("flux")
    if comfyui.ok and models.sd15_inpaint:
        local_inpaint.append("sd15")

    cloud_backends: list[str] = []
    if openai_configured:
        cloud_backends.append("openai")
    if dashscope_configured:
        cloud_backends.append("dashscope")

    txt2img_available = [*local_txt2img, *cloud_backends]
    inpaint_available = [*local_inpaint, *cloud_backends]
    txt2img_backend = txt2img_available[0] if txt2img_available else None
    inpaint_backend = inpaint_available[0] if inpaint_available else None
    txt2img_enabled = bool(txt2img_available)
    inpaint_enabled = bool(inpaint_available)

    decompose_sam = (
        comfyui.ok
        and models.flux_txt2img
        and models.sam2_segment
        and tier in {"gpu_24gb", "gpu_48gb"}
    )
    decompose_cloud = dashscope_configured
    decompose_local = comfyui.ok and models.sd15_inpaint and rembg_available()
    decompose_enabled = decompose_sam or decompose_cloud or decompose_local
    decompose_backend = (
        "dashscope_seg"
        if decompose_cloud
        else "flux_sam"
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

    image_edit_enabled = openai_configured
    image_edit_backend = "openai" if image_edit_enabled else None

    features: dict[str, FeatureCapability] = {
        "txt2img": FeatureCapability(
            enabled=txt2img_enabled,
            backend=txt2img_backend,
            available_backends=txt2img_available,
            reason=None
            if txt2img_enabled
            else _txt2img_reason(comfyui, local_txt2img, cloud_backends),
        ),
        "inpaint": FeatureCapability(
            enabled=inpaint_enabled,
            backend=inpaint_backend,
            available_backends=inpaint_available,
            reason=None
            if inpaint_enabled
            else _inpaint_reason(comfyui, local_inpaint, cloud_backends),
        ),
        "image_edit": FeatureCapability(
            enabled=image_edit_enabled,
            backend=image_edit_backend,
            available_backends=["openai"] if image_edit_enabled else [],
            reason=None
            if image_edit_enabled
            else "未配置 INFD_OPENAI_API_KEY（指令改图仅支持 OpenAI）",
        ),
        "controlled_edit": FeatureCapability(
            enabled=openai_configured,
            backend="openai" if openai_configured else None,
            available_backends=_controlled_edit_backends() if openai_configured else [],
            reason=None
            if openai_configured
            else "未配置 INFD_OPENAI_API_KEY（多轮可控编辑依赖 OpenAI 视觉与图像模型）",
            models=_controlled_edit_models(
                openai_configured=openai_configured,
                dashscope_configured=dashscope_configured,
            )
            if openai_configured
            else {},
        ),
        "plugin_t2i": FeatureCapability(
            enabled=txt2img_enabled,
            backend=txt2img_backend,
            available_backends=txt2img_available,
            reason=None if txt2img_enabled else "依赖 txt2img 能力",
        ),
        "decompose": FeatureCapability(
            enabled=decompose_enabled,
            backend=decompose_backend,
            available_backends=[decompose_backend] if decompose_backend else [],
            reason=None
            if decompose_enabled
            else _decompose_reason(comfyui, models, tier, dashscope_configured),
        ),
        "tab_inpaint": FeatureCapability(
            enabled=inpaint_enabled,
            backend=inpaint_backend,
            available_backends=inpaint_available,
            reason=None if inpaint_enabled else "依赖 inpaint 能力",
        ),
        "text_edit": FeatureCapability(
            enabled=text_edit_enabled,
            backend=text_edit_backend,
            available_backends=[text_edit_backend] if text_edit_backend else [],
            reason=None
            if text_edit_enabled
            else _text_edit_reason(comfyui, models),
        ),
        "asset_library": FeatureCapability(
            enabled=dashscope_configured or openai_configured,
            backend=(
                "dashscope"
                if dashscope_configured
                else "openai"
                if openai_configured
                else None
            ),
            available_backends=_asset_library_backends(
                dashscope_configured=dashscope_configured,
                openai_configured=openai_configured,
            ),
            reason=None
            if dashscope_configured or openai_configured
            else "未配置 DashScope 或 OpenAI API Key（素材标注需要视觉模型）",
            models={"scene": scene_model_name(settings)}
            if dashscope_configured or openai_configured
            else {},
        ),
    }
    return features


def _asset_library_backends(
    *,
    dashscope_configured: bool,
    openai_configured: bool,
) -> list[str]:
    backends: list[str] = []
    if dashscope_configured:
        backends.append("dashscope")
    if openai_configured:
        backends.append("openai")
    return backends


def _controlled_edit_backends() -> list[str]:
    if uses_dedicated_scene_model(settings):
        return ["openai", "dashscope"]
    return ["openai"]


def _controlled_edit_models(
    *,
    openai_configured: bool,
    dashscope_configured: bool,
) -> dict[str, str]:
    """Models and Studio pickers for controlled edit."""
    default_provider = settings.cedit_image_provider
    if default_provider == "dashscope" and not dashscope_configured:
        default_provider = "openai"
    if default_provider == "openai" and not openai_configured and dashscope_configured:
        default_provider = "dashscope"
    image_options: list[str] = []
    if dashscope_configured:
        image_options.append(f"dashscope|{settings.cedit_image_model}")
    if openai_configured:
        image_options.append(f"openai|{settings.openai_image_model}")
    return {
        "scene": scene_model_name(settings),
        "vision": settings.cedit_vision_model,
        "image": (
            settings.cedit_image_model
            if default_provider == "dashscope"
            else settings.openai_image_model
        ),
        "image_provider": default_provider,
        "image_options": ";".join(image_options),
        "lock_paste": "on" if settings.cedit_lock_paste else "off",
        "prompt_style": settings.cedit_prompt_style,
    }


def _txt2img_reason(
    comfyui: ServiceStatus,
    local_backends: list[str],
    cloud_backends: list[str],
) -> str:
    if local_backends or cloud_backends:
        return "生图能力不可用"
    if not comfyui.ok and not cloud_backends:
        return (
            f"ComfyUI 不可达（{comfyui.url}），且未配置 OpenAI/DashScope 图像 API Key"
        )
    if comfyui.ok and not local_backends:
        return "未安装 SD1.5/Flux checkpoint，且未配置云端图像 API Key"
    return "生图能力不可用"


def _inpaint_reason(
    comfyui: ServiceStatus,
    local_backends: list[str],
    cloud_backends: list[str],
) -> str:
    if local_backends or cloud_backends:
        return "inpaint 不可用"
    if not comfyui.ok and not cloud_backends:
        return (
            f"ComfyUI 不可达（{comfyui.url}），且未配置 OpenAI/DashScope 图像 API Key"
        )
    if comfyui.ok and not local_backends:
        return "未安装 SD1.5 inpaint/Flux Fill，且未配置云端图像 API Key"
    return "inpaint 不可用"


def _decompose_reason(
    comfyui: ServiceStatus,
    models: ModelsCapability,
    tier: str,
    dashscope_configured: bool,
) -> str:
    if dashscope_configured:
        return "元素拆解不可用"
    if not comfyui.ok and not dashscope_configured:
        return "未配置阿里云 API Key，且 ComfyUI/rembg 不可用"
    if not rembg_available():
        return "缺少 rembg，且未配置 INFD_DASHSCOPE_API_KEY"
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
    deepseek = await probe_deepseek()
    comfyui = await probe_comfyui()
    models = await probe_comfyui_models(comfyui.ok)
    dashscope_configured = bool(settings.dashscope_api_key.strip())
    openai_configured = bool(settings.openai_api_key.strip())

    tier = infer_tier(
        gpu,
        comfyui,
        models,
        dashscope_configured=dashscope_configured,
        openai_configured=openai_configured,
    )
    features = build_features(
        tier,
        comfyui,
        models,
        dashscope_configured=dashscope_configured,
        openai_configured=openai_configured,
    )

    return CapabilitiesResponse(
        tier=tier,
        gpu=gpu,
        services={
            "ollama": ollama,
            "deepseek": deepseek,
            "comfyui": comfyui,
            "openai_images": ServiceStatus(
                ok=openai_configured,
                url=settings.openai_base_url,
                remote=True,
            ),
            "dashscope": ServiceStatus(
                ok=dashscope_configured,
                url=settings.dashscope_base_url,
                remote=True,
            ),
        },
        models=models,
        features=features,
    )
