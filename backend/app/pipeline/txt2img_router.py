"""Resolve image backends from capabilities and request overrides."""

from __future__ import annotations

from fastapi import HTTPException

from app.pipeline.comfyui_client import ComfyUIClient
from app.pipeline.image_providers.factory import CLOUD_BACKENDS, LOCAL_BACKENDS
from app.system.capabilities import gather_capabilities

LOCAL_PREFERENCE = ("sd15", "flux")
CLOUD_PREFERENCE = ("openai", "dashscope")
KNOWN_BACKENDS = frozenset(
    {"auto", "local", "sd15", "flux", "openai", "dashscope"}
)


async def resolve_txt2img_backend(requested: str) -> str:
    """Resolve a txt2img backend (local ComfyUI or cloud provider)."""
    return await resolve_image_backend(requested, feature="txt2img")


async def resolve_inpaint_backend(requested: str) -> str:
    """Resolve an inpaint backend (local ComfyUI or cloud provider)."""
    return await resolve_image_backend(requested, feature="inpaint")


async def resolve_image_backend(requested: str, *, feature: str) -> str:
    """Pick a concrete backend from capabilities and an optional client hint."""
    if requested not in KNOWN_BACKENDS:
        raise HTTPException(status_code=400, detail=f"Unknown backend: {requested}")

    caps = await gather_capabilities()
    feature_cap = caps.features.get(feature)
    if not feature_cap or not feature_cap.enabled:
        raise HTTPException(
            status_code=503,
            detail=feature_cap.reason if feature_cap else f"{feature} unavailable",
        )

    available = list(feature_cap.available_backends)
    if not available and feature_cap.backend:
        available = [feature_cap.backend]

    if requested == "auto":
        resolved = _first_available(available, (*LOCAL_PREFERENCE, *CLOUD_PREFERENCE))
        if resolved is None:
            raise HTTPException(
                status_code=503,
                detail=feature_cap.reason or f"{feature} unavailable",
            )
        return resolved

    if requested == "local":
        resolved = _first_available(available, LOCAL_PREFERENCE)
        if resolved is None:
            raise HTTPException(
                status_code=503,
                detail="Local ComfyUI image backend is not available",
            )
        return resolved

    if requested in available:
        return requested

    if requested in LOCAL_BACKENDS | CLOUD_BACKENDS:
        raise HTTPException(
            status_code=503,
            detail=f"Backend '{requested}' is not available in current environment",
        )
    raise HTTPException(status_code=400, detail=f"Unknown backend: {requested}")


def _first_available(available: list[str], preference: tuple[str, ...]) -> str | None:
    available_set = set(available)
    for name in preference:
        if name in available_set:
            return name
    return None


async def build_txt2img_workflow_for_backend(
    client: ComfyUIClient,
    backend: str,
    *,
    prompt: str,
    negative_prompt: str,
    seed: int,
    steps: int,
) -> dict:
    """Build ComfyUI workflow for a local resolved backend."""
    if backend in CLOUD_BACKENDS:
        raise HTTPException(
            status_code=400,
            detail=f"Backend '{backend}' is a cloud provider, not a ComfyUI workflow",
        )
    if backend == "flux":
        if not client.has_flux_txt2img_workflow():
            raise HTTPException(
                status_code=503,
                detail="Flux workflow template missing on server",
            )
        return client.build_flux_txt2img_workflow(
            prompt=prompt,
            negative_prompt=negative_prompt,
            seed=seed,
            steps=min(steps, 8),
        )

    return client.build_txt2img_workflow(
        prompt=prompt,
        negative_prompt=negative_prompt,
        seed=seed,
        steps=steps,
    )
