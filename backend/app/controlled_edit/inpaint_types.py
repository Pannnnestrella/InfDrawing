"""Serializable contracts for masks and deterministic crop/stitch transforms."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InpaintOptions(BaseModel):
    """Mask processing parameters expressed in original-image pixels."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    threshold: float = Field(default=0.5, gt=0, le=1)
    fill_holes: bool = False
    dilate_px: int = Field(default=8, ge=0, le=128)
    feather_sigma_px: float = Field(default=4, ge=0, le=64)
    context_from_mask_extend_factor: float = Field(default=2, ge=1, le=8)
    min_context_px: int = Field(default=16, ge=0, le=512)
    model: Literal["wanx2.1-imageedit"] = "wanx2.1-imageedit"


class MaskRecord(BaseModel):
    """A mask bound to the exact source version and source image hash."""

    artifact_id: str
    source_artifact_id: str
    source_sha256: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    source: Literal["manual", "sam2", "sam3"] = "manual"
    score: float | None = None


class Stitcher(BaseModel):
    """Immutable inverse-transform metadata; coordinates are half-open source pixels."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    source_size: tuple[int, int]
    source_mode: Literal["RGB", "RGBA"]
    crop_rect: tuple[int, int, int, int]
    paste_rect: tuple[int, int, int, int]
    mask_bbox: tuple[int, int, int, int]
    padding: tuple[int, int, int, int]
    canvas_size: tuple[int, int]
    model_size: tuple[int, int]
    source_sha256: str
    source_artifact_id: str | None = None
    parent_version_id: str | None = None
    mask_artifact_id: str | None = None
    blend_artifact_id: str | None = None
    crop_artifact_id: str | None = None
    generation_mask_artifact_id: str | None = None
    actual_output_size: tuple[int, int] | None = None
    options: InpaintOptions


class LocalTurnFields(BaseModel):
    """Explicit local request fields with backward-compatible default behavior."""

    edit_mode: Literal["auto", "local", "full"] = "auto"
    mask_artifact_id: str | None = None
    inpaint_options: InpaintOptions = Field(default_factory=InpaintOptions)

    @model_validator(mode="after")
    def validate_mask_mode(self) -> "LocalTurnFields":
        """Prevent accidentally ignoring or widening an explicit mask."""
        if self.edit_mode == "local" and not self.mask_artifact_id:
            raise ValueError("local editing requires a mask_artifact_id")
        if self.mask_artifact_id and self.edit_mode != "local":
            raise ValueError("mask_artifact_id requires local edit_mode")
        return self
