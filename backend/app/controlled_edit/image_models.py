"""Catalog of full-frame and local edit models exposed to Studio."""

from __future__ import annotations

# DashScope models offered in the Studio full-frame picker (edit-capable only).
DASHSCOPE_FULLFRAME_MODELS: tuple[str, ...] = (
    "qwen-image-3.0-pro",
    "qwen-image-3.0",
    "qwen-image-2.0-pro",
    "qwen-image-2.0",
    "qwen-image-2.1-pro",
    "wan2.7-image-pro",
    "wan2.7-image",
)

WAN27_MODELS: frozenset[str] = frozenset({"wan2.7-image-pro", "wan2.7-image"})
QWEN_EDIT_MODELS: frozenset[str] = frozenset(
    {
        "qwen-image-3.0-pro",
        "qwen-image-3.0",
        "qwen-image-2.0-pro",
        "qwen-image-2.0",
        "qwen-image-2.1-pro",
        "qwen-image-2.1-turbo",
    }
)
