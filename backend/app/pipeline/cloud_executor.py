"""Run cloud image providers through the shared TaskState event contract."""

from __future__ import annotations

import uuid
from pathlib import Path

from app.config import settings
from app.pipeline.executor import TaskState, start_pipeline_task
from app.pipeline.image_providers import build_image_provider


async def run_cloud_txt2img_task(
    *,
    backend: str,
    prompt: str,
    negative_prompt: str,
    seed: int,
    outputs_dir: Path | None = None,
) -> TaskState:
    """Execute cloud txt2img and emit progress/complete events."""
    out_dir = outputs_dir or settings.outputs_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    provider = build_image_provider(backend)

    async def _pipeline(task: TaskState) -> None:
        image_bytes = await provider.txt2img(
            prompt=prompt,
            negative_prompt=negative_prompt,
            seed=seed,
            on_progress=task.emit_progress,
        )
        path = out_dir / f"{task.task_id}.png"
        path.write_bytes(image_bytes)
        task.image_path = path
        await task.emit_complete(f"/api/v1/files/outputs/{path.name}")

    return start_pipeline_task(str(uuid.uuid4()), _pipeline)


async def run_cloud_inpaint_task(
    *,
    backend: str,
    image_bytes: bytes,
    mask_bytes: bytes,
    prompt: str,
    negative_prompt: str,
    seed: int,
    outputs_dir: Path | None = None,
) -> TaskState:
    """Execute cloud inpaint and emit progress/complete events."""
    out_dir = outputs_dir or settings.outputs_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    provider = build_image_provider(backend)

    async def _pipeline(task: TaskState) -> None:
        result = await provider.inpaint(
            image_bytes=image_bytes,
            mask_bytes=mask_bytes,
            prompt=prompt,
            negative_prompt=negative_prompt,
            seed=seed,
            on_progress=task.emit_progress,
        )
        path = out_dir / f"{task.task_id}.png"
        path.write_bytes(result)
        task.image_path = path
        await task.emit_complete(f"/api/v1/files/outputs/{path.name}")

    return start_pipeline_task(str(uuid.uuid4()), _pipeline)


async def run_cloud_image_edit_task(
    *,
    backend: str,
    image_bytes: bytes,
    prompt: str,
    negative_prompt: str,
    seed: int,
    outputs_dir: Path | None = None,
) -> TaskState:
    """Execute maskless instruction image edit via a cloud provider."""
    out_dir = outputs_dir or settings.outputs_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    provider = build_image_provider(backend)

    async def _pipeline(task: TaskState) -> None:
        result = await provider.image_edit(
            image_bytes=image_bytes,
            prompt=prompt,
            negative_prompt=negative_prompt,
            seed=seed,
            on_progress=task.emit_progress,
        )
        path = out_dir / f"{task.task_id}.png"
        path.write_bytes(result)
        task.image_path = path
        await task.emit_complete(f"/api/v1/files/outputs/{path.name}")

    return start_pipeline_task(str(uuid.uuid4()), _pipeline)
