"""Factory helpers for image backends."""

from __future__ import annotations

from app.config import Settings, settings
from app.pipeline.image_providers.base import ImageProvider, ImageProviderError
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
