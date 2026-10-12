"""Lazy SAM 2.1 image segmentation with serialized predictor access."""

import importlib.util
import io
import threading
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps

from app.config import Settings
from app.controlled_edit.masks import png_bytes
from app.controlled_edit.segmentation import (
    SegmentationUnavailableError,
    SegmentRequest,
)

_lock = threading.Lock()
_predictor: Any = None
_predictor_key: tuple[str, str, str] | None = None


def sam2_ready(config: Settings) -> bool:
    """Check configuration without loading weights or initializing CUDA."""
    return bool(
        config.cedit_sam2_checkpoint
        and Path(config.cedit_sam2_checkpoint).is_file()
        and importlib.util.find_spec("sam2")
    )


def segment_sam2(
    data: bytes, prompt: SegmentRequest, config: Settings
) -> list[tuple[bytes, float]]:
    """Return candidate masks in source resolution using optional SAM 2 weights."""
    global _predictor, _predictor_key
    if not sam2_ready(config):
        raise SegmentationUnavailableError("SAM 2 未安装或未配置权重，请使用手工 Mask")
    from sam2.build_sam import build_sam2
    from sam2.sam2_image_predictor import SAM2ImagePredictor

    with Image.open(io.BytesIO(data)) as decoded:
        image = ImageOps.exif_transpose(decoded).convert("RGB")
    width, height = image.size
    points = np.asarray(prompt.points, dtype=np.float32).reshape(-1, 2) * [width, height]
    box = None
    if prompt.bbox:
        b = prompt.bbox
        box = np.array([b.x * width, b.y * height, (b.x + b.w) * width, (b.y + b.h) * height])
    key = (config.cedit_sam2_config, config.cedit_sam2_checkpoint, config.cedit_sam2_device)
    with _lock:
        if _predictor is None or _predictor_key != key:
            _predictor = SAM2ImagePredictor(build_sam2(key[0], key[1], device=key[2]))
            _predictor_key = key
        _predictor.set_image(np.array(image))
        masks, scores, _ = _predictor.predict(
            point_coords=points if prompt.points else None,
            point_labels=np.array(prompt.labels) if prompt.points else None,
            box=box,
            multimask_output=True,
        )
        return [
            (png_bytes(Image.fromarray(mask.astype(np.uint8) * 255)), float(score))
            for mask, score in zip(masks, scores, strict=True)
        ]
