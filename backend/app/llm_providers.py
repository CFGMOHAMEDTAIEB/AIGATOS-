"""Provider adapters. Only the selected provider is ever initialized."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable

from app.llm_config import LLMSettings


@dataclass(frozen=True)
class ProviderResult:
    content: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str) -> ProviderResult:
        raise NotImplementedError


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, settings: LLMSettings):
        from openai import OpenAI

        self.settings = settings
        self.client = OpenAI(
            api_key=settings.api_key.get_secret_value(),
            base_url=settings.base_url,
            timeout=settings.timeout_seconds,
            max_retries=settings.max_retries,
        )

    def generate(self, system_prompt: str, user_prompt: str) -> ProviderResult:
        response = self.client.chat.completions.create(
            model=self.settings.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=min(self.settings.temperature, 0.2),
            response_format={"type": "json_object"},
        )
        usage = response.usage
        return ProviderResult(
            content=response.choices[0].message.content or "",
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
            total_tokens=getattr(usage, "total_tokens", None),
        )


class NvidiaProvider(OpenAICompatibleProvider):
    pass


class DeepSeekProvider(OpenAICompatibleProvider):
    pass


class GoogleProvider(OpenAICompatibleProvider):
    pass


class KimiProvider(OpenAICompatibleProvider):
    pass


PROVIDER_REGISTRY: dict[str, Callable[[LLMSettings], LLMProvider]] = {
    "nvidia": NvidiaProvider,
    "deepseek": DeepSeekProvider,
    "google": GoogleProvider,
    "kimi": KimiProvider,
}


def get_provider(
    settings: LLMSettings,
    registry: dict[str, Callable[[LLMSettings], LLMProvider]] | None = None,
) -> LLMProvider:
    factories = registry or PROVIDER_REGISTRY
    factory = factories.get(settings.provider or "")
    if factory is None:
        raise ValueError("Unknown LLM provider")
    return factory(settings)
