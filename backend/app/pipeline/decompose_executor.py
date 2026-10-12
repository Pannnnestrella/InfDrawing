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
    is_named_decompose_prompt,
)
from app.storage.local import save_upload

logger = logging.getLogger(__name__)


def _store_named_layers(
    task_id: str,
    outputs_dir: Path,
    named_layers: list[tuple[str, bytes]],
) -> list[dict[str, str]]:
    """Write named PNG layers and return canvas layer records, background first."""
    stored: list[dict[str, str]] = []
    for index, (label, png) in enumerate(named_layers):
        raw_path = outputs_dir / f"{task_id}_named_{index}.png"
        rgba_path = outputs_dir / f"{task_id}_layer_{index}.png"
        raw_path.write_bytes(png)
        ensure_rgba_on_disk(raw_path, rgba_path)
        stored.append(
            {
                "label": label,
                "image_url": f"/api/v1/files/outputs/{rgba_path.name}",
            }
        )
    if not stored:
        raise ImageProviderError("named decompose produced no layers")
    return stored


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
        layers: list[dict[str, str]] = []
        named = is_named_decompose_prompt(background_prompt)
        if dashscope_decompose_available(settings):
            try:
                if named:
                    named_layers = await DashScopeDecomposeClient().split_named_layers(
                        image_bytes,
                        background_prompt,
                        on_progress=task.emit_progress,
                    )
                    layers = _store_named_layers(task.task_id, outputs_dir, named_layers)
                else:
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
                used_cloud = True
            except ImageProviderError as exc:
                logger.warning("cloud decompose failed, falling back if possible: %s", exc)
                # A named request must not silently become a two-layer rembg split.
                if named or not rembg_available():
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
            bg_rgba_path = outputs_dir / f"{task.task_id}_layer_bg.png"
            try:
                bg_file = await inpaint_image_files(
                    image_path,
                    mask_path,
                    prompt=background_prompt,
                    negative_prompt=negative_prompt,
                    outputs_dir=outputs_dir,
                )
                ensure_rgba_on_disk(bg_file, bg_rgba_path)
            except Exception as exc:  # noqa: BLE001 - keep a background if inpaint fails
                # ComfyUI may be down; still return rembg FG + source as BG.
                logger.warning("local inpaint failed, using source as background: %s", exc)
                bg_file = outputs_dir / f"{task.task_id}_erase.png"
                bg_file.write_bytes(image_bytes)
                ensure_rgba_on_disk(bg_file, bg_rgba_path)

        if not used_cloud:
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
        task.image_path = outputs_dir / Path(layers[0]["image_url"]).name
        await task.emit_complete(layers[0]["image_url"], layers=layers)

    return start_pipeline_task("decompose", _pipeline)
