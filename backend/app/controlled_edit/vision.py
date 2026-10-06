"""Minimal OpenAI-compatible vision chat client returning JSON objects."""

from __future__ import annotations

import base64
import io
import json
from typing import Any

import httpx
from PIL import Image

from app.config import Settings, settings

MAX_VISION_SIDE = 1024


class VisionError(RuntimeError):
    """Raised when the vision model cannot return a usable JSON object."""


def image_to_data_url(image_bytes: bytes, max_side: int = MAX_VISION_SIDE) -> str:
    """Downscale an image and encode it as a JPEG data URL for chat input."""
    with Image.open(io.BytesIO(image_bytes)) as image:
        rgb = image.convert("RGB")
        rgb.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        rgb.save(buffer, format="JPEG", quality=90)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def extract_json_object(raw: str) -> Any:
    """Parse a JSON reply, tolerating a surrounding Markdown code fence."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    return json.loads(text)


class VisionClient:
    """Call ``/chat/completions`` with optional images and parse a JSON object reply.

    Defaults to the OpenAI endpoint and ``cedit_vision_model``; ``base_url``, ``api_key``
    and ``model`` target any other OpenAI-compatible endpoint (e.g. DashScope).
    """

    def __init__(
        self,
        config: Settings = settings,
        client: httpx.AsyncClient | None = None,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._base_url = base_url or config.openai_base_url
        self._api_key = (config.openai_api_key if api_key is None else api_key).strip()
        self._model = model or config.cedit_vision_model
        if not self._api_key:
            raise VisionError(f"API key for {self._model} is not configured")
        config.validate_provider_url(self._base_url)
        self._config = config
        self._client = client

    @property
    def model(self) -> str:
        """Model id used for telemetry and debugging."""
        return self._model

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_text: str,
        images: list[bytes] | None = None,
    ) -> dict[str, Any]:
        """Return the model's JSON object reply.

        Args:
            system_prompt: Instructions including the expected JSON shape.
            user_text: Task-specific text placed before the images.
            images: Raw image bytes appended in order (image 1, image 2, ...).

        Raises:
            VisionError: On transport errors, HTTP errors, or non-object JSON.
        """
        content: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
        for image_bytes in images or []:
            content.append(
                {"type": "image_url", "image_url": {"url": image_to_data_url(image_bytes)}}
            )
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        url = f"{self._base_url.rstrip('/')}/chat/completions"
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=self._config.cedit_vision_timeout_seconds
        )
        try:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code >= 400:
                raise VisionError(
                    f"vision model error ({response.status_code}): {response.text[:300]}"
                )
            raw = response.json()["choices"][0]["message"]["content"]
            parsed = extract_json_object(raw)
        except httpx.HTTPError as exc:
            raise VisionError(f"vision request failed: {type(exc).__name__}") from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise VisionError(f"vision reply is not valid JSON: {type(exc).__name__}") from exc
        finally:
            if owns_client:
                await client.aclose()
        if not isinstance(parsed, dict):
            raise VisionError("vision reply must be a JSON object")
        return parsed


def uses_dedicated_scene_model(config: Settings = settings) -> bool:
    """Whether scene parsing runs on the dedicated grounding model (DashScope)."""
    return config.cedit_scene_provider == "dashscope" and bool(config.dashscope_api_key.strip())


def scene_model_name(config: Settings = settings) -> str:
    """Model id that scene parsing will use under the current configuration."""
    if uses_dedicated_scene_model(config):
        return config.cedit_scene_model
    return config.cedit_vision_model


def scene_vision_client(config: Settings = settings) -> VisionClient:
    """Build the client for scene parsing.

    Grounding needs accurate boxes, so the dedicated DashScope model is used when its
    key is configured; otherwise parsing falls back to the general vision model.
    """
    if uses_dedicated_scene_model(config):
        return VisionClient(
            config,
            base_url=config.cedit_scene_base_url,
            api_key=config.dashscope_api_key,
            model=config.cedit_scene_model,
        )
    return VisionClient(config)
