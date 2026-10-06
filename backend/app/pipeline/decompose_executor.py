"""Multi-step decompose task: segment → extract RGBA → inpaint background."""

from __future__ import annotations

import logging
from pathlib import Path

from app.config import settings
from app.pipeline.decompose import (
    extract_foreground_rgba,
    foreground_to_inpaint_mask,
    rembg_available,
)
from app.pipeline.executor import TaskState, inpaint_image_files, start_pipeline_task
from app.pipeline.image_io import ensure_rgba_on_disk, image_to_png_bytes
from app.pipeline.image_providers.base import ImageProviderError
from app.pipeline.image_providers.dashscope_decompose import (
    DashScopeDecomposeClient,
    dashscope_decompose_available,
)
from app.storage.local import save_upload

logger = logging.getLogger(__name__)


async def run_decompose_task(
    *,
    image_bytes: bytes,
    outputs_dir: Path,
    background_prompt: str = "clean seamless background, high quality",
    negative_prompt: str = "blurry, low quality, distorted, ugly",
) -> TaskState:
    """Start async decompose pipeline and return task handle."""

    async def _pipeline(task: TaskState) -> None:
        await task.emit_progress("segmenting")
        used_cloud = False
        if dashscope_decompose_available(settings):
            try:
                foreground, background = await DashScopeDecomposeClient().split_layers(
                    image_bytes,
                    on_progress=task.emit_progress,
                )
                fg_path = outputs_dir / f"{task.task_id}_layer_fg.png"
                foreground.save(fg_path, format="PNG")
                bg_rgba_path = outputs_dir / f"{task.task_id}_layer_bg.png"
                bg_file = outputs_dir / f"{task.task_id}_erase.png"
                bg_file.write_bytes(background)
                ensure_rgba_on_disk(bg_file, bg_rgba_path)
                used_cloud = True
            except ImageProviderError as exc:
                logger.warning("cloud decompose failed, falling back if possible: %s", exc)
                if not rembg_available():
                    raise
        if not used_cloud:
            if not rembg_available():
                raise RuntimeError("decompose requires DashScope API key or rembg")
            foreground = extract_foreground_rgba(image_bytes)
            fg_path = outputs_dir / f"{task.task_id}_layer_fg.png"
            foreground.save(fg_path, format="PNG")

            await task.emit_progress("extracting")
            mask_image = foreground_to_inpaint_mask(foreground)
            image_path = save_upload(f"{task.task_id}_source.png", image_bytes)
            mask_path = save_upload(f"{task.task_id}_mask.png", image_to_png_bytes(mask_image))

            await task.emit_progress("inpainting")
            bg_file = await inpaint_image_files(
                image_path,
                mask_path,
                prompt=background_prompt,
                negative_prompt=negative_prompt,
                outputs_dir=outputs_dir,
            )
            bg_rgba_path = outputs_dir / f"{task.task_id}_layer_bg.png"
            ensure_rgba_on_disk(bg_file, bg_rgba_path)

        layers = [
            {"label": "background", "image_url": f"/api/v1/files/outputs/{bg_rgba_path.name}"},
            {"label": "foreground", "image_url": f"/api/v1/files/outputs/{fg_path.name}"},
        ]
        task.image_path = bg_rgba_path
        await task.emit_complete(layers[0]["image_url"], layers=layers)

    return start_pipeline_task("decompose", _pipeline)
