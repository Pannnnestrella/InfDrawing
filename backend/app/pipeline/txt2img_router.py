"""Resolve txt2img backend from capabilities and request override."""

from fastapi import HTTPException

from app.pipeline.comfyui_client import ComfyUIClient
from app.system.capabilities import gather_capabilities


async def resolve_txt2img_backend(requested: str) -> str:
    """Pick sd15 or flux based on capabilities and optional client hint."""
    caps = await gather_capabilities()
    feature = caps.features.get("txt2img")
    if not feature or not feature.enabled:
        raise HTTPException(
            status_code=503,
            detail=feature.reason if feature else "txt2img unavailable",
        )

    detected = feature.backend or "sd15"
    if requested == "auto":
        return detected

    if requested in {"sd15", "flux"}:
        if requested == "flux" and detected != "flux":
            raise HTTPException(
                status_code=503,
                detail="Flux backend not available in current environment",
            )
        return requested

    raise HTTPException(status_code=400, detail=f"Unknown backend: {requested}")


async def build_txt2img_workflow_for_backend(
    client: ComfyUIClient,
    backend: str,
    *,
    prompt: str,
    negative_prompt: str,
    seed: int,
    steps: int,
) -> dict:
    """Build ComfyUI workflow for the resolved backend."""
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
