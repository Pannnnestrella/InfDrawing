"""Shared interface for cloud image providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable


ProgressCallback = Callable[[str], Awaitable[None]]


class ImageProviderError(RuntimeError):
    """Raised when a cloud image provider fails."""


class ImageProvider(ABC):
    """Generate or edit images and return raw PNG/JPEG bytes."""

    name: str

    @abstractmethod
    async def txt2img(
        self,
        *,
        prompt: str,
        negative_prompt: str = "",
        seed: int = 42,
        on_progress: ProgressCallback | None = None,
    ) -> bytes:
        """Create an image from a text prompt."""

    @abstractmethod
    async def inpaint(
        self,
        *,
        image_bytes: bytes,
        mask_bytes: bytes,
        prompt: str,
        negative_prompt: str = "",
        seed: int = 42,
        on_progress: ProgressCallback | None = None,
    ) -> bytes:
        """Edit the masked region of an image."""

    async def image_edit(
        self,
        *,
        image_bytes: bytes,
        prompt: str,
        negative_prompt: str = "",
        seed: int = 42,
        on_progress: ProgressCallback | None = None,
    ) -> bytes:
        """Instruction-based edit without a mask (optional capability)."""
        raise ImageProviderError(f"{self.name} does not support maskless image_edit")


async def emit_progress(callback: ProgressCallback | None, step: str) -> None:
    """Invoke an optional progress callback."""
    if callback is not None:
        await callback(step)
