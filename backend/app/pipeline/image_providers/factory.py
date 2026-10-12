"""Factory helpers for image backends."""

from __future__ import annotations

from app.config import Settings, settings
from app.pipeline.image_providers.base import ImageProvider, ImageProviderError
from app.pipeline.image_providers.dashscope_qwen_edit import DashScopeQwenEditProvider
from app.pipeline.image_providers.dashscope_wanx import DashScopeWanxProvider
from app.pipeline.image_providers.openai_images import OpenAIImageProvider

CLOUD_BACKENDS = frozenset({"openai", "dashscope"})
LOCAL_BACKENDS = frozenset({"sd15", "flux", "local"})


def is_cloud_backend(backend: str) -> bool:
    """Return True when the resolved backend is a cloud image provider."""
    return backend in CLOUD_BACKENDS


def build_image_provider(backend: str, config: Settings = settings) -> ImageProvider:
    """Construct a cloud image provider for the resolved backend name."""
    if backend == "openai":
        return OpenAIImageProvider(config=config)
    if backend == "dashscope":
        return DashScopeWanxProvider(config=config)
    raise ImageProviderError(f"unsupported cloud image backend: {backend}")


def build_sidebar_image_provider(
    backend: str,
    role: str,
    config: Settings = settings,
) -> ImageProvider:
    """Provider for sidebar txt2img / instruction edit.

    DashScope here is Qwen Image, not Wanx. Masked inpaint does not use this path.
    """
    if backend == "openai":
        return OpenAIImageProvider(config=config)
    if backend == "dashscope" and role in {"txt2img", "image_edit"}:
        return DashScopeQwenEditProvider(config=config, model=config.qwen_image_model)
    if backend == "dashscope" and role == "inpaint":
        raise ImageProviderError("masked inpaint uses OpenAI, not Wanx")
    raise ImageProviderError(f"unsupported cloud image backend: {backend}")
