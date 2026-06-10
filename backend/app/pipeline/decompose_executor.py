"""Multi-step decompose task: segment → extract RGBA → inpaint background."""

from __future__ import annotations

import asyncio
import io
import uuid
from pathlib import Path
from typing import Any

from PIL import Image

from app.pipeline.comfyui_client import ComfyUIClient
from app.pipeline.decompose import extract_foreground_rgba, foreground_to_inpaint_mask
from app.pipeline.executor import TaskState, task_manager
from app.storage.local import save_upload


async def _wait_comfyui_output(
    client: ComfyUIClient,
    prompt_id: str,
    outputs_dir: Path,
    *,
    timeout: float = 300.0,
    poll_interval: float = 2.0,
) -> Path:
    elapsed = 0.0
    while elapsed < timeout:
        history = await client.get_history(prompt_id)
        if prompt_id in history:
            copied = await client.copy_output_image(prompt_id, outputs_dir)
            if copied:
                return copied
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
    raise TimeoutError("ComfyUI inpaint timed out")


async def _emit(task: TaskState, payload: dict[str, Any]) -> None:
    await task.events.put(payload)


def _image_to_png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _ensure_rgba_on_disk(src: Path, dest: Path) -> None:
    with Image.open(src) as image:
        image.convert("RGBA").save(dest, format="PNG")


async def run_decompose_task(
    *,
    image_bytes: bytes,
    outputs_dir: Path,
    background_prompt: str = "clean seamless background, high quality",
    negative_prompt: str = "blurry, low quality, distorted, ugly",
) -> TaskState:
    """Start async decompose pipeline and return task handle."""
    task = TaskState(task_id=str(uuid.uuid4()), prompt_id="decompose")
    task_manager.register(task)

    async def _pipeline() -> None:
        try:
            task.status = "running"
            await _emit(
                task,
                {"type": "progress", "task_id": task.task_id, "step": "segmenting"},
            )

            foreground = extract_foreground_rgba(image_bytes)
            fg_path = outputs_dir / f"{task.task_id}_layer_fg.png"
            foreground.save(fg_path, format="PNG")

            await _emit(
                task,
                {"type": "progress", "task_id": task.task_id, "step": "extracting"},
            )

            mask_image = foreground_to_inpaint_mask(foreground)
            image_path = save_upload(f"{task.task_id}_source.png", image_bytes)
            mask_path = save_upload(f"{task.task_id}_mask.png", _image_to_png_bytes(mask_image))

            await _emit(
                task,
                {"type": "progress", "task_id": task.task_id, "step": "inpainting"},
            )

            client = ComfyUIClient()
            image_name = await client.upload_image(image_path)
            mask_name = await client.upload_image(mask_path)
            workflow = client.build_inpaint_workflow(
                image_name=image_name,
                mask_name=mask_name,
                prompt=background_prompt,
                negative_prompt=negative_prompt,
            )
            prompt_id = await client.queue_prompt(workflow)
            bg_file = await _wait_comfyui_output(client, prompt_id, outputs_dir)
            bg_rgba_path = outputs_dir / f"{task.task_id}_layer_bg.png"
            _ensure_rgba_on_disk(bg_file, bg_rgba_path)

            layers = [
                {
                    "label": "background",
                    "image_url": f"/api/v1/files/outputs/{bg_rgba_path.name}",
                },
                {
                    "label": "foreground",
                    "image_url": f"/api/v1/files/outputs/{fg_path.name}",
                },
            ]

            task.status = "complete"
            task.image_path = bg_rgba_path
            await _emit(
                task,
                {
                    "type": "complete",
                    "task_id": task.task_id,
                    "image_url": layers[0]["image_url"],
                    "layers": layers,
                },
            )
        except Exception as exc:
            task.status = "error"
            task.error = str(exc)
            await _emit(
                task,
                {"type": "error", "task_id": task.task_id, "message": str(exc)},
            )

    asyncio.create_task(_pipeline())
    return task
