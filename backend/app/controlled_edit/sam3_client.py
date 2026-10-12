"""Client for an explicitly configured independent SAM 3 image service."""

import base64

import httpx

from app.config import Settings
from app.controlled_edit.segmentation import (
    SegmentationUnavailableError,
    SegmentRequest,
)


async def segment_sam3(
    image: bytes, prompt: SegmentRequest, config: Settings
) -> list[tuple[bytes, float]]:
    """Use our adapter contract: POST /segment returning masks and scores.

    This is an InfDrawing service contract, not a claim of a standard SAM 3 API.
    """
    if not config.cedit_sam3_base_url:
        raise SegmentationUnavailableError("未配置独立 SAM 3 服务，请使用 SAM 2 或手工 Mask")
    config.validate_provider_url(config.cedit_sam3_base_url)
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            f"{config.cedit_sam3_base_url.rstrip('/')}/segment",
            json={
                "image_base64": base64.b64encode(image).decode(),
                "prompt": prompt.model_dump(mode="json"),
            },
        )
        response.raise_for_status()
        candidates = response.json()["masks"]
        if not isinstance(candidates, list) or not 1 <= len(candidates) <= 10:
            raise ValueError("SAM 3 returned an invalid candidate count")
        return [
            (base64.b64decode(item["png_base64"], validate=True), float(item["score"]))
            for item in candidates
        ]
