"""Pydantic models for system capability probes."""

from pydantic import BaseModel, Field


class GpuInfo(BaseModel):
    """Detected local NVIDIA GPU state."""

    available: bool
    name: str | None = None
    vram_total_mb: int | None = None
    vram_free_mb: int | None = None


class ServiceStatus(BaseModel):
    """Health of an external dependency."""

    ok: bool
    url: str
    remote: bool = False


class ModelsCapability(BaseModel):
    """Which ComfyUI model families appear installed."""

    sd15_txt2img: bool = False
    sd15_inpaint: bool = False
    flux_txt2img: bool = False
    sam2_segment: bool = False
    flux_fill: bool = False
    anytext2: bool = False


class FeatureCapability(BaseModel):
    """User-facing feature gate."""

    enabled: bool
    backend: str | None = None
    reason: str | None = None


class CapabilitiesResponse(BaseModel):
    """Full environment capability snapshot."""

    tier: str
    gpu: GpuInfo
    services: dict[str, ServiceStatus]
    models: ModelsCapability
    features: dict[str, FeatureCapability] = Field(default_factory=dict)
