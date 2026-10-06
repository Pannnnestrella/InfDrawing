"""DashScope Wanx provider (async txt2img + masked image edit)."""

from __future__ import annotations

import asyncio
import base64
import io
import uuid
from typing import Any
from urllib.parse import urlparse

import httpx
from PIL import Image

from app.config import Settings, settings
from app.pipeline.image_providers.base import (
    ImageProvider,
    ImageProviderError,
    ProgressCallback,
    emit_progress,
)

WANX_MIN_SIDE = 512


class DashScopeWanxProvider(ImageProvider):
    """Call DashScope Wanx text-to-image and image-edit APIs."""

    name = "dashscope"

    def __init__(self, config: Settings = settings, client: httpx.AsyncClient | None = None) -> None:
        if not config.dashscope_api_key.strip():
            raise ImageProviderError("DashScope API key is not configured")
        config.validate_provider_url(config.dashscope_base_url)
        self._config = config
        self._client = client

    async def txt2img(
        self,
        *,
        prompt: str,
        negative_prompt: str = "",
        seed: int = 42,
        on_progress: ProgressCallback | None = None,
    ) -> bytes:
        """Generate an image via Wanx text-to-image async API."""
        await emit_progress(on_progress, "cloud_submit")
        payload = {
            "model": self._config.dashscope_t2i_model,
            "input": {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
            },
            "parameters": {
                "size": "1024*1024",
                "n": 1,
                "seed": seed,
            },
        }
        task_id = await self._submit_async(
            "/services/aigc/text2image/image-synthesis",
            payload,
        )
        await emit_progress(on_progress, "cloud_poll")
        result_url = await self._poll_task_image_url(task_id)
        await emit_progress(on_progress, "cloud_download")
        return await self._download_bytes(result_url)

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
        """Inpaint via wanx2.1-imageedit description_edit_with_mask.

        Official API: white RGB (255,255,255) is edited, black (0,0,0) is kept.
        Images are sent as documented ``data:image/png;base64,...`` URLs so the
        call does not depend on the OSS getPolicy upload path.
        """
        del negative_prompt  # Wanx edit API has no negative_prompt field.
        return await self.inpaint_from_urls(
            prompt=prompt,
            base_image_url=_png_data_url(_ensure_min_side(image_bytes)),
            mask_image_url=_png_data_url(_ensure_min_side(mask_bytes, nearest=True)),
            seed=seed,
            on_progress=on_progress,
        )

    async def inpaint_from_urls(
        self,
        *,
        prompt: str,
        base_image_url: str,
        mask_image_url: str,
        seed: int = 42,
        on_progress: ProgressCallback | None = None,
    ) -> bytes:
        """Call ``description_edit_with_mask`` with already-hosted or data URLs."""
        await emit_progress(on_progress, "cloud_submit")
        payload = {
            "model": self._config.dashscope_edit_model,
            "input": {
                "function": "description_edit_with_mask",
                "prompt": prompt,
                "base_image_url": base_image_url,
                "mask_image_url": mask_image_url,
            },
            "parameters": {
                "n": 1,
                "seed": seed,
            },
        }
        task_id = await self._submit_async(
            "/services/aigc/image2image/image-synthesis",
            payload,
        )
        await emit_progress(on_progress, "cloud_poll")
        result_url = await self._poll_task_image_url(task_id)
        await emit_progress(on_progress, "cloud_download")
        return await self._download_bytes(result_url)

    async def _submit_async(self, path: str, payload: dict[str, Any]) -> str:
        headers = {
            "Authorization": f"Bearer {self._config.dashscope_api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }
        if _contains_oss_url(payload):
            headers["X-DashScope-OssResourceResolve"] = "enable"
        data = await self._request("POST", path, headers=headers, json=payload)
        task_id = (
            data.get("output", {}).get("task_id")
            if isinstance(data.get("output"), dict)
            else None
        )
        if not isinstance(task_id, str) or not task_id:
            raise ImageProviderError("DashScope response missing task_id")
        return task_id

    async def _poll_task_image_url(self, task_id: str) -> str:
        headers = {"Authorization": f"Bearer {self._config.dashscope_api_key}"}
        elapsed = 0.0
        timeout = self._config.cloud_image_timeout_seconds
        interval = self._config.cloud_image_poll_seconds
        while elapsed < timeout:
            data = await self._request(
                "GET",
                f"/tasks/{task_id}",
                headers=headers,
            )
            output = data.get("output") if isinstance(data.get("output"), dict) else {}
            status = str(output.get("task_status", "")).upper()
            if status == "SUCCEEDED":
                return _extract_result_url(output)
            if status in {"FAILED", "CANCELED", "UNKNOWN"}:
                message = output.get("message") or data.get("message") or status
                raise ImageProviderError(f"DashScope task failed: {message}")
            await asyncio.sleep(interval)
            elapsed += interval
        raise ImageProviderError(f"DashScope task timed out (last_status={status or 'empty'})")

    async def _upload_temp_url(self, content: bytes, *, filename: str, model: str) -> str:
        """Upload bytes via DashScope getPolicy and return an oss:// URL."""
        headers = {"Authorization": f"Bearer {self._config.dashscope_api_key}"}
        policy = await self._request(
            "GET",
            f"/uploads?action=getPolicy&model={model}",
            headers=headers,
            validate_host=False,
        )
        data = policy.get("data") if isinstance(policy.get("data"), dict) else {}
        upload_host = data.get("upload_host")
        upload_dir = data.get("upload_dir")
        if not isinstance(upload_host, str) or not isinstance(upload_dir, str):
            raise ImageProviderError(
                "DashScope upload policy incomplete; cannot obtain temporary image URL"
            )
        key = f"{upload_dir.rstrip('/')}/{uuid.uuid4().hex}_{filename}"
        form = {
            "OSSAccessKeyId": data.get("oss_access_key_id", ""),
            "Signature": data.get("signature", ""),
            "policy": data.get("policy", ""),
            "x-oss-object-acl": data.get("x_oss_object_acl", "private"),
            "x-oss-forbid-overwrite": data.get("x_oss_forbid_overwrite", "true"),
            "key": key,
            "success_action_status": "200",
        }
        files = {"file": (filename, content, "image/png")}
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=self._config.cloud_image_timeout_seconds
        )
        try:
            response = await client.post(upload_host, data=form, files=files)
            if response.status_code >= 400:
                raise ImageProviderError(
                    f"DashScope file upload failed ({response.status_code})"
                )
        except httpx.HTTPError as exc:
            raise ImageProviderError(
                f"DashScope file upload failed: {type(exc).__name__}"
            ) from exc
        finally:
            if owns_client:
                await client.aclose()

        # DashScope accepts oss:// URLs produced from the upload policy key.
        return f"oss://{key}" if not key.startswith("oss://") else key

    async def _download_bytes(self, url: str) -> bytes:
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
                f"DashScope image download failed: {type(exc).__name__}"
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
        validate_host: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        base = self._config.dashscope_base_url.rstrip("/")
        url = path if path.startswith("http") else f"{base}{path}"
        if validate_host:
            self._config.validate_provider_url(url if "://" in url else base)
        else:
            # Upload policy host may be OSS; still require absolute HTTPS in production.
            parsed = urlparse(url if "://" in url else base)
            if self._config.environment == "production" and parsed.scheme != "https":
                raise ImageProviderError("DashScope URL must use HTTPS in production")

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=self._config.cloud_image_timeout_seconds
        )
        try:
            response = await client.request(method, url, headers=headers, **kwargs)
            if response.status_code >= 400:
                raise ImageProviderError(
                    f"DashScope error ({response.status_code}): "
                    f"{(response.text or 'unknown')[:300]}"
                )
            return response.json()
        except httpx.HTTPError as exc:
            raise ImageProviderError(
                f"DashScope request failed: {type(exc).__name__}"
            ) from exc
        finally:
            if owns_client:
                await client.aclose()


def _extract_result_url(output: dict[str, Any]) -> str:
    results = output.get("results")
    if isinstance(results, list) and results:
        url = results[0].get("url") if isinstance(results[0], dict) else None
        if isinstance(url, str) and url:
            return url
    # Some edit APIs nest under output.choices / output.output_image_url
    for key in ("output_image_url", "output_mask_url", "url"):
        value = output.get(key)
        if isinstance(value, str) and value:
            return value
    raise ImageProviderError("DashScope task succeeded but returned no image URL")


def _contains_oss_url(value: Any) -> bool:
    """Return True if any nested string uses the DashScope oss:// scheme."""
    if isinstance(value, str):
        return value.startswith("oss://")
    if isinstance(value, dict):
        return any(_contains_oss_url(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_oss_url(item) for item in value)
    return False


def _png_data_url(image_bytes: bytes) -> str:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _ensure_min_side(image_bytes: bytes, *, nearest: bool = False) -> bytes:
    """Upscale so both sides are at least 512px, as Wanx requires."""
    with Image.open(io.BytesIO(image_bytes)) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        if width >= WANX_MIN_SIDE and height >= WANX_MIN_SIDE:
            if image.format == "PNG" and not nearest:
                return image_bytes
            buffer = io.BytesIO()
            rgb.save(buffer, format="PNG")
            return buffer.getvalue()
        scale = max(WANX_MIN_SIDE / width, WANX_MIN_SIDE / height)
        resample = Image.Resampling.NEAREST if nearest else Image.Resampling.LANCZOS
        rgb = rgb.resize((round(width * scale), round(height * scale)), resample)
        buffer = io.BytesIO()
        rgb.save(buffer, format="PNG")
        return buffer.getvalue()
