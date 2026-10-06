"""OpenAI Images API provider (txt2img + edits/inpaint)."""

from __future__ import annotations

import base64
from typing import Any

import httpx

from app.config import Settings, settings
from app.pipeline.image_providers.base import (
    ImageProvider,
    ImageProviderError,
    ProgressCallback,
    emit_progress,
)


class OpenAIImageProvider(ImageProvider):
    """Call OpenAI Images generations and edits endpoints."""

    name = "openai"

    def __init__(self, config: Settings = settings, client: httpx.AsyncClient | None = None) -> None:
        if not config.openai_api_key.strip():
            raise ImageProviderError("OpenAI API key is not configured")
        config.validate_provider_url(config.openai_base_url)
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
        """Generate an image via /images/generations."""
        del seed  # OpenAI Images API does not accept a public seed parameter.
        await emit_progress(on_progress, "cloud_submit")
        full_prompt = prompt
        if negative_prompt.strip():
            full_prompt = f"{prompt}\n\nAvoid: {negative_prompt.strip()}"
        payload: dict[str, Any] = {
            "model": self._config.openai_image_model,
            "prompt": full_prompt,
            "n": 1,
            "size": "1024x1024",
        }
        data = await self._post_json("/images/generations", payload)
        await emit_progress(on_progress, "cloud_download")
        return await self._extract_image_bytes(data)

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
        """Edit a masked region via /images/edits."""
        return await self._edits(
            image_bytes=image_bytes,
            mask_bytes=mask_bytes,
            prompt=prompt,
            negative_prompt=negative_prompt,
            seed=seed,
            on_progress=on_progress,
        )

    async def image_edit(
        self,
        *,
        image_bytes: bytes,
        prompt: str,
        negative_prompt: str = "",
        seed: int = 42,
        on_progress: ProgressCallback | None = None,
    ) -> bytes:
        """Instruction-based edit via /images/edits without a mask."""
        return await self._edits(
            image_bytes=image_bytes,
            mask_bytes=None,
            prompt=prompt,
            negative_prompt=negative_prompt,
            seed=seed,
            on_progress=on_progress,
        )

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
        """Edit ``image_bytes`` with extra reference images via /images/edits.

        The primary image is sent first, followed by ``reference_images`` in order. If
        the API rejects ``input_fidelity`` the request is retried once without it.
        """
        await emit_progress(on_progress, "cloud_submit")
        files: list[tuple[str, tuple[str, bytes, str]]] = [
            ("image[]", ("image_1.png", image_bytes, "image/png"))
        ]
        for index, reference in enumerate(reference_images, start=2):
            files.append(("image[]", (f"image_{index}.png", reference, "image/png")))
        form: dict[str, str] = {
            "model": self._config.openai_image_model,
            "prompt": prompt,
            "n": "1",
            "size": size,
        }
        if input_fidelity:
            form["input_fidelity"] = input_fidelity
        try:
            data = await self._request("POST", "/images/edits", data=form, files=files)
        except ImageProviderError as exc:
            if "input_fidelity" not in form or "input_fidelity" not in str(exc):
                raise
            form.pop("input_fidelity")
            data = await self._request("POST", "/images/edits", data=form, files=files)
        await emit_progress(on_progress, "cloud_download")
        return await self._extract_image_bytes(data)

    async def _edits(
        self,
        *,
        image_bytes: bytes,
        mask_bytes: bytes | None,
        prompt: str,
        negative_prompt: str,
        seed: int,
        on_progress: ProgressCallback | None,
    ) -> bytes:
        del seed
        await emit_progress(on_progress, "cloud_submit")
        full_prompt = prompt
        if negative_prompt.strip():
            full_prompt = f"{prompt}\n\nAvoid: {negative_prompt.strip()}"
        files: dict[str, tuple[str, bytes, str]] = {
            "image": ("image.png", image_bytes, "image/png"),
        }
        if mask_bytes is not None:
            files["mask"] = ("mask.png", mask_bytes, "image/png")
        form = {
            "model": self._config.openai_image_model,
            "prompt": full_prompt,
            "n": "1",
            "size": "1024x1024",
        }
        data = await self._post_multipart("/images/edits", data=form, files=files)
        await emit_progress(on_progress, "cloud_download")
        return await self._extract_image_bytes(data)

    async def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", path, json=payload)

    async def _post_multipart(
        self,
        path: str,
        *,
        data: dict[str, str],
        files: dict[str, tuple[str, bytes, str]],
    ) -> dict[str, Any]:
        return await self._request("POST", path, data=data, files=files)

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._config.openai_api_key}"}
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=self._config.cloud_image_timeout_seconds
        )
        url = f"{self._config.openai_base_url.rstrip('/')}{path}"
        try:
            response = await client.request(method, url, headers=headers, **kwargs)
            if response.status_code >= 400:
                detail = _safe_error_detail(response)
                raise ImageProviderError(f"OpenAI Images error ({response.status_code}): {detail}")
            return response.json()
        except httpx.HTTPError as exc:
            raise ImageProviderError(f"OpenAI Images request failed: {type(exc).__name__}") from exc
        finally:
            if owns_client:
                await client.aclose()

    async def _extract_image_bytes(self, payload: dict[str, Any]) -> bytes:
        try:
            item = payload["data"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise ImageProviderError("OpenAI Images response missing image data") from exc
        if isinstance(item.get("b64_json"), str):
            return base64.b64decode(item["b64_json"])
        url = item.get("url")
        if not isinstance(url, str) or not url:
            raise ImageProviderError("OpenAI Images response missing image url/b64")
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
                f"OpenAI image download failed: {type(exc).__name__}"
            ) from exc
        finally:
            if owns_client:
                await client.aclose()


def _safe_error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
        error = body.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return error["message"][:300]
        if isinstance(body.get("message"), str):
            return body["message"][:300]
    except ValueError:
        pass
    return (response.text or "unknown error")[:300]
