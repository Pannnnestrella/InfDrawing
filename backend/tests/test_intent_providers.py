"""Tests for intent LLM provider factory."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.agent.providers import (
    OpenAICompatibleProvider,
    ProviderError,
    build_intent_provider,
    intent_model_name,
)
from app.config import Settings


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def _settings(**overrides: object) -> Settings:
    base = {
        "llm_provider": "deepseek",
        "deepseek_api_key": "sk-ds-test",
        "deepseek_base_url": "https://api.deepseek.com/v1",
        "deepseek_model": "deepseek-chat",
        "openai_api_key": "",
        "provider_allowed_hosts": [
            "api.openai.com",
            "api.deepseek.com",
            "127.0.0.1",
            "localhost",
        ],
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_build_deepseek_provider() -> None:
    provider = build_intent_provider(_settings())
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.model == "deepseek-chat"
    assert provider.structured_format == "json_object"


def test_build_deepseek_requires_key() -> None:
    with pytest.raises(ProviderError, match="DeepSeek"):
        build_intent_provider(_settings(deepseek_api_key=""))


def test_intent_model_name_deepseek() -> None:
    assert intent_model_name(_settings()) == "deepseek-chat"


def test_deepseek_classify_uses_json_object() -> None:
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": (
                        '{"intent":"txt2img","refined_prompt":"a cat",'
                        '"negative_prompt":"blurry","target_tool":"comfyui_txt2img_v1",'
                        '"params":{},"confidence":0.9,"reasoning":"ok",'
                        '"clarification_required":false}'
                    )
                }
            }
        ]
    }
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post = AsyncMock(return_value=response)
    client.aclose = AsyncMock()

    provider = OpenAICompatibleProvider(
        base_url="https://api.deepseek.com/v1",
        model="deepseek-chat",
        api_key="sk-test",
        config=_settings(),
        client=client,
        structured_format="json_object",
    )
    plan = _run(provider.classify("system", "draw a cat"))
    assert plan.intent.value == "txt2img"
    payload = client.post.await_args.kwargs["json"]
    assert payload["response_format"] == {"type": "json_object"}
