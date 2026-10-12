"""Optional segmentation contracts without importing heavyweight model packages."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.controlled_edit.schemas import BBox


class SegmentRequest(BaseModel):
    """Prompts in normalized source coordinates."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    provider: Literal["sam2", "sam3"] = "sam2"
    bbox: BBox | None = None
    points: list[tuple[float, float]] = Field(default_factory=list, max_length=100)
    labels: list[Literal[0, 1]] = Field(default_factory=list, max_length=100)
    text: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def check_prompts(self) -> "SegmentRequest":
        """Reject missing, mismatched, or out-of-frame prompts."""
        if len(self.points) != len(self.labels):
            raise ValueError("point and label counts must match")
        if any(not 0 <= value <= 1 for point in self.points for value in point):
            raise ValueError("points must use normalized image coordinates")
        if not self.bbox and not self.points and not self.text:
            raise ValueError("segmentation requires a box, points, or text")
        if self.provider == "sam2" and self.text:
            raise ValueError("SAM 2 requires visual prompts, not text")
        return self


class SegmentationUnavailableError(RuntimeError):
    """Raised when an optional model or service is not configured."""
