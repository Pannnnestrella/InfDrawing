"""DashScope Wan 2.7 multimodal image edit (instruction + optional bbox_list)."""

from __future__ import annotations

import base64
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import Settings, settings
from app.pipeline.image_providers.base import (
    ImageProvider,
    ImageProviderError,
    ProgressCallback,
    emit_progress,
)

WAN27_EDIT_PATH = "/services/aigc/multimodal-generation/generation"
MAX_INPUT_IMAGES = 9


class DashScopeWan27EditProvider(ImageProvider):
    """Call ``wan2.7-image`` / ``wan2.7-image-pro`` via multimodal generation.

    Image order matches Qwen (references first, primary last) so aspect follows the
    artwork being edited. ``bbox_list`` entries align 1:1 with content images.
    """

    name = "dashscope_wan27_edit"
    prompt_image_layout = "primary_last"

    def __init__(
        self,
        config: Settings = settings,
        client: httpx.AsyncClient | None = None,
        *,
        model: str | None = None,
    ) -> None:
        if not config.dashscope_api_key.strip():
            raise ImageProviderError("DashScope API key is not configured")
        config.validate_provider_url(config.dashscope_base_url)
        self._config = config
        self._client = client
        self._model = (model or config.cedit_auto_local_model or "wan2.7-image-pro").strip()

    async def txt2img(
        self,
        *,
        prompt: str,
        negative_prompt: str = "",
        seed: int = 42,
        on_progress: ProgressCallback | None = None,
    ) -> bytes:
        del prompt, negative_prompt, seed, on_progress
        raise ImageProviderError("DashScopeWan27EditProvider does not implement txt2img")

    async def inpaint(
        self,
        *,
        image_bytes: bytes,
        mask_bytes: bytes,
        prompt: str,
        negative_prompt: str = "",
        seed: int = 42,
        on_progress: ProgressCallback | None = None,
    ) -> bytes:
        del image_bytes, mask_bytes, prompt, negative_prompt, seed, on_progress
        raise ImageProviderError(
            "Wan 2.7 has no binary mask field; use multi_image_edit with bbox_list"
        )

    async def multi_image_edit(
        self,
        *,
        image_bytes: bytes,
        reference_images: list[bytes],
        prompt: str,
        size: str = "2K",
        input_fidelity: str | None = None,
        bbox_list: list[list[list[int]]] | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> bytes:
        """Edit ``image_bytes`` with optional references and per-image boxes."""
        del input_fidelity
        await emit_progress(on_progress, "cloud_submit")
        refs = reference_images[: MAX_INPUT_IMAGES - 1]
        content: list[dict[str, str]] = [{"image": _data_url(item)} for item in refs]
        content.append({"image": _data_url(image_bytes)})
        content.append({"text": prompt[:5000]})
        parameters: dict[str, Any] = {
            "n": 1,
            "watermark": False,
            "size": _normalize_size(size),
        }
        if bbox_list is not None:
            if len(bbox_list) != len(refs) + 1:
                raise ImageProviderError(
                    "bbox_list length must match the number of input images"
                )
            parameters["bbox_list"] = bbox_list
        payload = {
            "model": self._model,
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": parameters,
        }
        headers = {
            "Authorization": f"Bearer {self._config.dashscope_api_key}",
            "Content-Type": "application/json",
        }
        data = await self._request(
            "POST",
            WAN27_EDIT_PATH,
            headers=headers,
            json=payload,
            timeout=self._config.cloud_image_timeout_seconds,
        )
        url = _extract_image_url(data)
        await emit_progress(on_progress, "cloud_download")
        return await self._download_bytes(url)

    async def _download_bytes(self, url: str) -> bytes:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ImageProviderError("Wan 2.7 returned an invalid image URL")
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=self._config.cloud_image_timeout_seconds
        )
        try:
            response = await client.get(url)
            response.raise_for_status()
            return response.content
        except httpx.HTTPError as exc:
            raise ImageProviderError(
                f"Wan 2.7 image download failed: {type(exc).__name__}"
            ) from exc
        finally:
            if owns_client:
                await client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str],
        **kwargs: Any,
    ) -> dict[str, Any]:
        base = self._config.dashscope_base_url.rstrip("/")
        self._config.validate_provider_url(base)
        url = f"{base}{path}"
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=self._config.cloud_image_timeout_seconds
        )
        try:
            response = await client.request(method, url, headers=headers, **kwargs)
            if response.status_code >= 400:
                raise ImageProviderError(
                    f"Wan 2.7 edit error ({response.status_code}): "
                    f"{(response.text or 'unknown')[:300]}"
                )
            return response.json()
        except httpx.HTTPError as exc:
            raise ImageProviderError(
                f"Wan 2.7 edit request failed: {type(exc).__name__}"
            ) from exc
        finally:
            if owns_client:
                await client.aclose()


def _data_url(image_bytes: bytes) -> str:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _normalize_size(size: str) -> str:
    """Accept ``2K`` / ``1K`` or ``WxH`` / ``W*H`` forms."""
    value = size.strip()
    upper = value.upper()
    if upper in {"1K", "2K", "4K"}:
        return upper
    if "x" in value.lower():
        width, height = value.lower().split("x", 1)
        return f"{width.strip()}*{height.strip()}"
    return value


def _extract_image_url(payload: dict[str, Any]) -> str:
    output = payload.get("output")
    if not isinstance(output, dict):
        raise ImageProviderError("Wan 2.7 reply missing output")
    choices = output.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("image"), str):
                    return item["image"]
    results = output.get("results")
    if isinstance(results, list) and results:
        first = results[0]
        if isinstance(first, dict) and isinstance(first.get("url"), str):
            return first["url"]
    raise ImageProviderError("Wan 2.7 reply contained no image URL")
