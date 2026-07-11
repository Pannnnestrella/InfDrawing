"""Async text-edit task: erase OCR region via inpaint, return overlay metadata."""

from __future__ import annotations

import io
import json
from pathlib import Path

from PIL import Image

from app.pipeline.executor import TaskState, inpaint_image_files, start_pipeline_task
from app.pipeline.image_io import image_to_png_bytes
from app.pipeline.text_edit import bbox_to_inpaint_mask
from app.storage.local import save_upload


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
    bbox = _parse_bbox(bbox_json)

    async def _pipeline(task: TaskState) -> None:
        await task.emit_progress("masking")
        with Image.open(io.BytesIO(image_bytes)) as source:
            width, height = source.size

        mask_image = bbox_to_inpaint_mask(width, height, bbox)
        image_path = save_upload(f"{task.task_id}_source.png", image_bytes)
        mask_path = save_upload(f"{task.task_id}_mask.png", image_to_png_bytes(mask_image))

        await task.emit_progress("inpainting")
        output_file = await inpaint_image_files(
            image_path,
            mask_path,
            prompt=inpaint_prompt,
            negative_prompt=negative_prompt,
            outputs_dir=outputs_dir,
        )

        task.image_path = output_file
        await task.emit_complete(
            f"/api/v1/files/outputs/{output_file.name}",
            overlay={
                "text": new_text,
                "bbox": list(bbox),
                "image_width": width,
                "image_height": height,
            },
        )

    return start_pipeline_task("text_edit", _pipeline)
