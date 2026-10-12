"""Model-specific contracts for local image editing, independent of credentials."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class InpaintCapability:
    """Describe documented input and requested output constraints.

    Attributes:
        mask_mode: How the provider receives an editing mask.
        input_min: Minimum accepted input side, when documented.
        input_max: Maximum accepted input side, when documented.
        max_bytes: Maximum encoded file size before Base64 transport.
        min_area: Minimum requested output pixel area.
        max_area: Maximum requested output pixel area.
        max_ratio: Maximum output long-side to short-side ratio.
        multiple: Requested size alignment; not an output-size guarantee.
        experimental: Whether local editing still needs hosted-model validation.
    """

    mask_mode: Literal["binary_field", "image_prompt", "unsupported"]
    input_min: int
    input_max: int
    max_bytes: int
    min_area: int
    max_area: int
    max_ratio: float
    multiple: int = 1
    experimental: bool = False
    documented_on: str = "2026-10-12"

    def validate_input(self, size: tuple[int, int], size_bytes: int = 0) -> None:
        """Reject inputs outside the provider's documented limits."""
        if any(side < self.input_min or side > self.input_max for side in size):
            raise ValueError("image dimensions exceed provider input limits")
        if size_bytes > self.max_bytes:
            raise ValueError("image file exceeds provider byte limit")

    def validate_output(self, size: tuple[int, int]) -> None:
        """Validate a requested working canvas, not a returned image."""
        width, height = size
        if min(size) <= 0 or not self.min_area <= width * height <= self.max_area:
            raise ValueError("requested output pixel area exceeds provider limits")
        if max(size) / min(size) > self.max_ratio:
            raise ValueError("requested output aspect ratio exceeds provider limits")
        if any(side % self.multiple for side in size):
            raise ValueError("requested dimensions must align to provider size multiple")


def inpaint_capability(model: str) -> InpaintCapability:
    """Return an explicit capability; never silently accept an unknown model."""
    if model == "wanx2.1-imageedit":
        # Output sizing is not a documented guarantee; use a conservative square canvas.
        return InpaintCapability("binary_field", 512, 4096, 10_000_000, 1024**2, 1024**2, 1)
    if model.startswith("qwen-image-2.0"):
        return InpaintCapability("unsupported", 1, 8000, 10_000_000, 512**2, 2048**2, 8, 16)
    if model in {"qwen-image-2.1-pro", "qwen-image-2.1-turbo"}:
        return InpaintCapability(
            "image_prompt", 1, 8000, 10_000_000, 512**2, 2048**2, 8, experimental=True
        )
    if model in {"wan2.7-image", "wan2.7-image-pro"}:
        return InpaintCapability("unsupported", 240, 8000, 20_000_000, 768**2, 2048**2, 8)
    raise ValueError(f"unknown local editing model: {model}")
