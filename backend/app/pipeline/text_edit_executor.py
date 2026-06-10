"""Async text-edit task: erase OCR region via inpaint, return overlay metadata."""

from __future__ import annotations

import asyncio
import io
import json
import uuid
from pathlib import Path
from typing import Any

from PIL import Image

from app.pipeline.comfyui_client import ComfyUIClient
from app.pipeline.executor import TaskState, task_manager
from app.pipeline.text_edit import bbox_to_inpaint_mask
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


def _parse_bbox(raw: str) -> tuple[int, int, int, int]:
    data = json.loads(raw)
    if not isinstance(data, list) or len(data) != 4:
        raise ValueError("bbox must be a JSON array of four integers")
    return int(data[0]), int(data[1]), int(data[2]), int(data[3])


async def run_text_edit_task(
    *,
    image_bytes: bytes,
    bbox_json: str,
    new_text: str,
    outputs_dir: Path,
    inpaint_prompt: str = "clean seamless background, high quality",
    negative_prompt: str = "blurry, low quality, distorted, ugly, text, letters",
) -> TaskState:
    """Erase text at bbox via inpaint; frontend overlays new_text on canvas."""
    task = TaskState(task_id=str(uuid.uuid4()), prompt_id="text_edit")
    task_manager.register(task)
    bbox = _parse_bbox(bbox_json)

    async def _pipeline() -> None:
        try:
            task.status = "running"
            await _emit(
                task,
                {"type": "progress", "task_id": task.task_id, "step": "masking"},
            )

            with Image.open(io.BytesIO(image_bytes)) as source:
                width, height = source.size

            mask_image = bbox_to_inpaint_mask(width, height, bbox)
            image_path = save_upload(f"{task.task_id}_source.png", image_bytes)
            mask_path = save_upload(
                f"{task.task_id}_mask.png",
                _image_to_png_bytes(mask_image),
            )

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
                prompt=inpaint_prompt,
                negative_prompt=negative_prompt,
            )
            prompt_id = await client.queue_prompt(workflow)
            output_file = await _wait_comfyui_output(client, prompt_id, outputs_dir)

            task.status = "complete"
            task.image_path = output_file
            await _emit(
                task,
                {
                    "type": "complete",
                    "task_id": task.task_id,
                    "image_url": f"/api/v1/files/outputs/{output_file.name}",
                    "overlay": {
                        "text": new_text,
                        "bbox": list(bbox),
                        "image_width": width,
                        "image_height": height,
                    },
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
