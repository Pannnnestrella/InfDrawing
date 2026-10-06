"""Structured LLM providers used by the intent router."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.agent.schemas import IntentPlan
from app.config import Settings, settings


class ProviderError(RuntimeError):
    """Raised when an LLM provider cannot return a valid structured result."""


class IntentProvider(ABC):
    """Interface for structured intent classification providers."""

    @abstractmethod
    async def classify(self, system_prompt: str, user_prompt: str) -> IntentPlan:
        """Classify a user request into a validated intent plan."""


class OpenAICompatibleProvider(IntentProvider):
    """Call an OpenAI-compatible chat completions endpoint."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        config: Settings = settings,
        client: httpx.AsyncClient | None = None,
        structured_format: str = "json_schema",
    ) -> None:
        config.validate_provider_url(base_url)
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.structured_format = structured_format
        self._client = client

    async def classify(self, system_prompt: str, user_prompt: str) -> IntentPlan:
        """Return a schema-validated plan from a compatible provider."""
        if self.structured_format == "json_object":
            response_format: dict[str, Any] = {"type": "json_object"}
            system_content = (
                f"{system_prompt}\n\n"
                "Respond with a single JSON object that matches this schema:\n"
                f"{IntentPlan.model_json_schema()}"
            )
        else:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "intent_plan",
                    "strict": False,
                    "schema": IntentPlan.model_json_schema(),
                },
            }
            system_content = system_prompt

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "response_format": response_format,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30.0)
        try:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return IntentPlan.model_validate_json(content)
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise ProviderError(f"intent provider failed: {type(exc).__name__}") from exc
        finally:
            if owns_client:
                await client.aclose()


class OllamaProvider(OpenAICompatibleProvider):
    """Ollama provider using its OpenAI-compatible endpoint."""

    async def classify(self, system_prompt: str, user_prompt: str) -> IntentPlan:
        """Return a schema-validated plan from Ollama."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "format": IntentPlan.model_json_schema(),
        }
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30.0)
        try:
            response = await client.post(f"{self.base_url}/chat/completions", json=payload)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return IntentPlan.model_validate_json(content)
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise ProviderError(f"intent provider failed: {type(exc).__name__}") from exc
        finally:
            if owns_client:
                await client.aclose()


def build_intent_provider(config: Settings = settings) -> IntentProvider:
    """Build the configured intent provider."""
    if config.llm_provider == "openai":
        if not config.openai_api_key:
            raise ProviderError("OpenAI API key is not configured")
        return OpenAICompatibleProvider(
            base_url=config.openai_base_url,
            model=config.openai_model,
            api_key=config.openai_api_key,
            config=config,
        )
    if config.llm_provider == "deepseek":
        if not config.deepseek_api_key:
            raise ProviderError("DeepSeek API key is not configured")
        # DeepSeek supports json_object, not OpenAI-style json_schema.
        return OpenAICompatibleProvider(
            base_url=config.deepseek_base_url,
            model=config.deepseek_model,
            api_key=config.deepseek_api_key,
            config=config,
            structured_format="json_object",
        )
    if config.llm_provider == "ollama":
        return OllamaProvider(
            base_url=config.ollama_base_url,
            model=config.ollama_model,
            config=config,
        )
    raise ProviderError(f"unsupported LLM provider: {config.llm_provider}")


def intent_model_name(config: Settings = settings) -> str:
    """Return the configured model id for telemetry."""
    if config.llm_provider == "openai":
        return config.openai_model
    if config.llm_provider == "deepseek":
        return config.deepseek_model
    if config.llm_provider == "ollama":
        return config.ollama_model
    return config.llm_provider
