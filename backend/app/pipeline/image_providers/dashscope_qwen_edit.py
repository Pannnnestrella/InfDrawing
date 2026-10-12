"""DashScope Qwen image-edit provider (multi-image instruction edits)."""

from __future__ import annotations

import asyncio
import base64
import uuid
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

QWEN_EDIT_PATH = "/services/aigc/multimodal-generation/generation"
QWEN_ASYNC_PATH = "/services/aigc/image-generation/generation"
MAX_INPUT_IMAGES = 3


class DashScopeQwenEditProvider(ImageProvider):
    """Call DashScope Qwen image-edit (default ``qwen-image-2.0``) with optional references.

    The Qwen API uses the last image's aspect ratio for the output, so references are
    sent first and the image being edited is sent last.
    """

    name = "dashscope_qwen_edit"
    prompt_image_layout = "primary_last"

    def __init__(
        self, config: Settings = settings, client: httpx.AsyncClient | None = None
    ) -> None:
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
        """Not used by controlled edit; Wanx remains the text-to-image backend."""
        del prompt, negative_prompt, seed, on_progress
        raise ImageProviderError("DashScopeQwenEditProvider does not implement txt2img")

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
        """Not used by controlled edit."""
        del image_bytes, mask_bytes, prompt, negative_prompt, seed, on_progress
        raise ImageProviderError("DashScopeQwenEditProvider does not implement inpaint")

    async def multi_image_edit(
        self,
        *,
        image_bytes: bytes,
        reference_images: list[bytes],
        prompt: str,
        size: str = "1024x1024",
        input_fidelity: str | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> bytes:
        """Edit ``image_bytes`` with optional identity references.

        Args:
            image_bytes: Current artwork (sent last so output matches its aspect).
            reference_images: Locked-entity crops; at most two are kept.
            prompt: Compiled edit instructions.
            size: OpenAI-style ``WxH``; converted to DashScope ``W*H``.
            input_fidelity: Ignored; Qwen has no equivalent parameter.
            on_progress: Optional progress hook.
        """
        del input_fidelity
        await emit_progress(on_progress, "cloud_submit")
        if self._config.cedit_image_model.startswith("qwen-image-2.1-"):
            task = await self.submit_edit_task(
                image_bytes=image_bytes, reference_images=reference_images, prompt=prompt, size=size
            )
            await emit_progress(on_progress, f"cloud_task:{task['task_id']}")
            return await self.wait_edit_task(task["task_id"], on_progress=on_progress)
        refs = reference_images[: MAX_INPUT_IMAGES - 1]
        content: list[dict[str, str]] = [{"image": _data_url(item)} for item in refs]
        content.append({"image": _data_url(image_bytes)})
        content.append({"text": prompt})
        payload = {
            "model": self._config.cedit_image_model,
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": {
                "n": 1,
                "watermark": False,
                "prompt_extend": False,
                "size": size.replace("x", "*"),
            },
        }
        headers = {
            "Authorization": f"Bearer {self._config.dashscope_api_key}",
            "Content-Type": "application/json",
        }
        data = await self._request("POST", QWEN_EDIT_PATH, headers=headers, json=payload)
        url = _extract_image_url(data)
        await emit_progress(on_progress, "cloud_download")
        return await self._download_bytes(url)

    async def submit_edit_task(
        self,
        *,
        image_bytes: bytes,
        reference_images: list[bytes],
        prompt: str,
        size: str = "1024x1024",
        upload_images: bool = False,
    ) -> dict[str, str]:
        """Submit once and return trace identifiers for persistent polling."""
        if not self._config.cedit_image_model.startswith("qwen-image-2.1-"):
            raise ImageProviderError("asynchronous editing is enabled only for Qwen 2.1")
        images = [*reference_images[:2], image_bytes]
        urls = (
            [await self.upload_temporary_image(item) for item in images]
            if upload_images
            else [_data_url(item) for item in images]
        )
        content = [{"image": url} for url in urls]
        content.append({"text": prompt})
        payload = {
            "model": self._config.cedit_image_model,
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": {
                "n": 1,
                "watermark": False,
                "prompt_extend": False,
                "size": size.replace("x", "*"),
            },
        }
        headers = {
            "Authorization": f"Bearer {self._config.dashscope_api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }
        if upload_images:
            headers["X-DashScope-OssResourceResolve"] = "enable"
        data = await self._request(
            "POST",
            QWEN_ASYNC_PATH,
            headers=headers,
            json=payload,
            timeout=60.0,
        )
        output = data.get("output", {})
        task_id = output.get("task_id") if isinstance(output, dict) else None
        if not isinstance(task_id, str) or not task_id:
            raise ImageProviderError("Qwen async response missing task_id")
        return {"task_id": task_id, "request_id": str(data.get("request_id", ""))}

    async def upload_temporary_image(self, image: bytes) -> str:
        """Upload lossless PNG bytes to the model's free temporary storage."""
        model = self._config.cedit_image_model
        data = await self._request(
            "GET",
            "/uploads",
            headers={"Authorization": f"Bearer {self._config.dashscope_api_key}"},
            params={"action": "getPolicy", "model": model},
            timeout=30.0,
        )
        policy = data.get("data", {})
        required = ("upload_host", "upload_dir", "oss_access_key_id", "signature", "policy")
        if not isinstance(policy, dict) or any(not policy.get(key) for key in required):
            raise ImageProviderError("Qwen temporary upload policy is incomplete")
        host = urlparse(policy["upload_host"])
        if host.scheme != "https" or not host.hostname:
            raise ImageProviderError("Qwen temporary upload host must use HTTPS")
        key = f"{policy['upload_dir'].rstrip('/')}/{uuid.uuid4().hex}.png"
        form = {
            "OSSAccessKeyId": policy["oss_access_key_id"],
            "Signature": policy["signature"],
            "policy": policy["policy"],
            "key": key,
            "success_action_status": "200",
            "x-oss-object-acl": policy.get("x_oss_object_acl", "private"),
            "x-oss-forbid-overwrite": policy.get("x_oss_forbid_overwrite", "true"),
        }
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=60.0)
        try:
            response = await client.post(
                policy["upload_host"],
                data=form,
                files={"file": ("input.png", image, "image/png")},
                timeout=60.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ImageProviderError(f"Qwen temporary upload failed: {type(exc).__name__}") from exc
        finally:
            if owns_client:
                await client.aclose()
        return f"oss://{key}"

    async def wait_edit_task(
        self,
        task_id: str,
        *,
        timeout_seconds: float = 600.0,
        on_progress: ProgressCallback | None = None,
    ) -> bytes:
        """Poll an existing task without resubmitting a paid generation request."""
        if not task_id or any(
            c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
            for c in task_id
        ):
            raise ValueError("invalid Qwen task ID")
        headers = {"Authorization": f"Bearer {self._config.dashscope_api_key}"}
        await emit_progress(on_progress, "cloud_poll")
        failures = 0
        try:
            async with asyncio.timeout(timeout_seconds):
                while True:
                    try:
                        data = await self._request(
                            "GET", f"/tasks/{task_id}", headers=headers, timeout=30.0
                        )
                    except ImageProviderError as exc:
                        if not isinstance(exc.__cause__, httpx.TransportError):
                            raise
                        failures += 1
                        if failures >= 3:
                            raise ImageProviderError(
                                f"Qwen polling interrupted; task_id={task_id}; resume this task"
                            ) from exc
                        await asyncio.sleep(max(0.01, self._config.cloud_image_poll_seconds))
                        continue
                    failures = 0
                    output = data.get("output", {})
                    state = output.get("task_status") if isinstance(output, dict) else None
                    if state == "SUCCEEDED":
                        url = _extract_image_url(data)
                        await emit_progress(on_progress, "cloud_download")
                        return await self._download_bytes(url)
                    if state in {"FAILED", "CANCELED", "UNKNOWN"}:
                        raise ImageProviderError(
                            f"Qwen task {state}; task_id={task_id}; "
                            f"{output.get('code', '')}: {output.get('message', '')}"
                        )
                    if state not in {"PENDING", "RUNNING"}:
                        raise ImageProviderError(f"Qwen invalid task status; task_id={task_id}")
                    await asyncio.sleep(max(0.01, self._config.cloud_image_poll_seconds))
        except TimeoutError as exc:
            raise ImageProviderError(
                f"Qwen polling timed out; task_id={task_id}; resume this task without resubmitting"
            ) from exc

    async def _download_bytes(self, url: str) -> bytes:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ImageProviderError("Qwen edit returned an invalid image URL")
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._config.cloud_image_timeout_seconds)
        try:
            response = await client.get(url)
            response.raise_for_status()
            return response.content
        except httpx.HTTPError as exc:
            raise ImageProviderError(
                f"Qwen edit image download failed: {type(exc).__name__}"
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
        client = self._client or httpx.AsyncClient(timeout=self._config.cloud_image_timeout_seconds)
        try:
            response = await client.request(method, url, headers=headers, **kwargs)
            if response.status_code >= 400:
                raise ImageProviderError(
                    f"Qwen edit error ({response.status_code}): "
                    f"{(response.text or 'unknown')[:300]}"
                )
            return response.json()
        except httpx.HTTPError as exc:
            raise ImageProviderError(f"Qwen edit request failed: {type(exc).__name__}") from exc
        finally:
            if owns_client:
                await client.aclose()


def _data_url(image_bytes: bytes) -> str:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _extract_image_url(payload: dict[str, Any]) -> str:
    output = payload.get("output")
    if not isinstance(output, dict):
        raise ImageProviderError("Qwen edit reply missing output")
    choices = output.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ImageProviderError("Qwen edit reply missing choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        raise ImageProviderError("Qwen edit reply missing image content")
    for item in content:
        if isinstance(item, dict) and isinstance(item.get("image"), str):
            return item["image"]
    raise ImageProviderError("Qwen edit reply contained no image URL")
