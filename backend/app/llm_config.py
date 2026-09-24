"""Secret-safe, provider-neutral Phase 4A configuration."""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


PROJECT_ROOT = Path(__file__).resolve().parents[2]
NVIDIA_DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_DEFAULT_MODEL = "z-ai/glm-5.3"
PROVIDER_ENV = {
    "nvidia": ("NVIDIA_API_KEY", "NVIDIA_BASE_URL", "NVIDIA_MODEL"),
    "deepseek": ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"),
    "google": ("GOOGLE_API_KEY", "GOOGLE_BASE_URL", "GOOGLE_MODEL"),
    "kimi": ("KIMI_API_KEY", "KIMI_BASE_URL", "KIMI_MODEL"),
}


class LLMConfigurationError(ValueError):
    pass


class LLMSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key: SecretStr | None = None
    api_key_variable: str | None = None
    temperature: float = Field(default=0.2, ge=0, le=0.2)
    timeout_seconds: float = Field(default=30, gt=0, le=120)
    max_retries: int = Field(default=0, ge=0, le=2)

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.provider and self.model and self.base_url and self.api_key)

    @model_validator(mode="after")
    def validate_selected_provider(self) -> "LLMSettings":
        if not self.enabled:
            return self
        if self.provider not in PROVIDER_ENV:
            raise LLMConfigurationError("Unknown LLM provider")
        missing = []
        if self.api_key is None or not self.api_key.get_secret_value():
            missing.append(self.api_key_variable or "provider API key")
        if not self.model:
            missing.append("provider model")
        if not self.base_url:
            missing.append("provider base URL")
        if missing:
            raise LLMConfigurationError("Missing LLM configuration: " + ", ".join(missing))
        return self


def _optional_env(name: str) -> str | None:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else None


def load_llm_settings(*, load_local_env: bool = True) -> LLMSettings:
    if load_local_env:
        load_dotenv(PROJECT_ROOT / ".env", override=False)
    enabled = (_optional_env("LLM_ENABLED") or "false").lower() in {"1", "true", "yes"}
    provider = (_optional_env("LLM_PROVIDER") or "").lower() or None
    if provider not in PROVIDER_ENV:
        if enabled:
            raise LLMConfigurationError("Unknown LLM provider")
        return LLMSettings(enabled=False, provider=provider)
    key_variable, base_variable, model_variable = PROVIDER_ENV[provider]
    base_url = _optional_env(base_variable)
    provider_model = _optional_env(model_variable)
    if provider == "nvidia":
        base_url = base_url or NVIDIA_DEFAULT_BASE_URL
    return LLMSettings(
        enabled=enabled,
        provider=provider,
        model=_optional_env("LLM_MODEL") or provider_model,
        base_url=base_url,
        api_key=SecretStr(os.getenv(key_variable)) if os.getenv(key_variable) else None,
        api_key_variable=key_variable,
        temperature=float(_optional_env("LLM_TEMPERATURE") or "0.2"),
        timeout_seconds=float(_optional_env("LLM_TIMEOUT_SECONDS") or "30"),
        max_retries=int(_optional_env("LLM_MAX_RETRIES") or "0"),
    )


def safe_url(url: str | None) -> str:
    if not url:
        return ""
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    if parsed.port:
        host += f":{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))


def redact_secrets(message: str, settings: LLMSettings | None = None) -> str:
    redacted = str(message)
    if settings and settings.api_key:
        secret = settings.api_key.get_secret_value()
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    redacted = re.sub(r"(?i)(authorization|api[_-]?key|token|password)\s*[=:]\s*[^\s,;]+", r"\1=[REDACTED]", redacted)
    redacted = re.sub(r"://([^:/\s]+):([^@/\s]+)@", r"://\1:[REDACTED]@", redacted)
    return redacted[:1000]
