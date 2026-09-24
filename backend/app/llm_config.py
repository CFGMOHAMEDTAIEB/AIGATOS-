"""Secret-safe multi-provider LLM configuration."""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOGGER = logging.getLogger("aigatos.llm")
PROVIDER_ENV = {
    "nvidia": ("NVIDIA_API_KEY", "NVIDIA_BASE_URL", "NVIDIA_MODEL"),
    "google": ("GOOGLE_API_KEY", "GOOGLE_BASE_URL", "GOOGLE_MODEL"),
    "openai": ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"),
    "deepseek": ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"),
    "kimi": ("KIMI_API_KEY", "KIMI_BASE_URL", "KIMI_MODEL"),
}
PROVIDER_DEFAULTS: dict[str, tuple[str | None, str | None]] = {
    "nvidia": ("https://integrate.api.nvidia.com/v1", "z-ai/glm-5.3-flash"),
    "google": ("https://generativelanguage.googleapis.com/v1beta/openai/", None),
    "openai": ("https://api.openai.com/v1", "gpt-4.1-mini"),
    "deepseek": ("https://api.deepseek.com/v1", None),
    "kimi": ("https://api.moonshot.ai/v1", None),
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
    connect_timeout_seconds: float = Field(default=5, gt=0, le=30)
    read_timeout_seconds: float = Field(default=30, gt=0, le=120)
    write_timeout_seconds: float = Field(default=10, gt=0, le=60)
    pool_timeout_seconds: float = Field(default=5, gt=0, le=30)
    max_retries: int = Field(default=1, ge=0, le=2)
    max_output_tokens: int = Field(default=1200, ge=64, le=4096)

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.provider and self.model and self.base_url and self.api_key)

    @property
    def max_attempts(self) -> int:
        return 1 + min(self.max_retries, 1)

    @model_validator(mode="after")
    def validate_selected_provider(self):
        if not self.enabled:
            return self
        if self.provider not in PROVIDER_ENV:
            raise LLMConfigurationError("Unknown LLM provider")
        missing=[]
        if self.api_key is None or not self.api_key.get_secret_value(): missing.append(self.api_key_variable or "provider API key")
        if not self.model: missing.append("provider model")
        if not self.base_url: missing.append("provider base URL")
        if missing: raise LLMConfigurationError("Missing LLM configuration: " + ", ".join(missing))
        return self


def _optional_env(name: str) -> str | None:
    value=os.getenv(name)
    return value.strip() if value and value.strip() else None


def load_llm_settings(*, load_local_env: bool=True) -> LLMSettings:
    if load_local_env:
        load_dotenv(PROJECT_ROOT / ".env", override=False)
    enabled=(_optional_env("LLM_ENABLED") or "false").lower() in {"1","true","yes"}
    provider=(_optional_env("LLM_PROVIDER") or "").lower() or None
    if provider not in PROVIDER_ENV:
        if enabled: raise LLMConfigurationError("Unknown LLM provider")
        return LLMSettings(enabled=False,provider=provider)
    key_var,base_var,model_var=PROVIDER_ENV[provider]
    default_url,default_model=PROVIDER_DEFAULTS[provider]
    base_url=_optional_env(base_var) or default_url
    # Explicit global override, then provider-specific model, then a provider-valid default.
    model=_optional_env("LLM_MODEL") or _optional_env(model_var) or default_model
    general_timeout=float(_optional_env("LLM_TIMEOUT_SECONDS") or "30")
    settings=LLMSettings(
        enabled=enabled,provider=provider,model=model,base_url=base_url,
        api_key=SecretStr(os.getenv(key_var)) if os.getenv(key_var) else None,api_key_variable=key_var,
        temperature=float(_optional_env("LLM_TEMPERATURE") or "0.2"),timeout_seconds=general_timeout,
        connect_timeout_seconds=float(_optional_env("LLM_CONNECT_TIMEOUT_SECONDS") or "5"),
        read_timeout_seconds=float(_optional_env("LLM_READ_TIMEOUT_SECONDS") or str(general_timeout)),
        write_timeout_seconds=float(_optional_env("LLM_WRITE_TIMEOUT_SECONDS") or "10"),
        pool_timeout_seconds=float(_optional_env("LLM_POOL_TIMEOUT_SECONDS") or "5"),
        max_retries=int(_optional_env("LLM_MAX_RETRIES") or "1"),
        max_output_tokens=int(_optional_env("LLM_MAX_OUTPUT_TOKENS") or "1200"),
    )
    return settings


def safe_url(url: str | None) -> str:
    if not url: return ""
    parsed=urlsplit(url);host=parsed.hostname or ""
    if parsed.port: host+=f":{parsed.port}"
    return urlunsplit((parsed.scheme,host,parsed.path,"",""))


def safe_settings(settings: LLMSettings) -> dict:
    parsed=urlsplit(settings.base_url or "")
    return {"provider":settings.provider,"model":settings.model,"hostname":parsed.hostname or "","configured":settings.configured,"connect_timeout":settings.connect_timeout_seconds,"read_timeout":settings.read_timeout_seconds,"retry":min(settings.max_retries,1)}


def log_llm_settings(settings: LLMSettings) -> None:
    LOGGER.info("LLM configuration: %s", safe_settings(settings))


def redact_secrets(message: str, settings: LLMSettings | None=None) -> str:
    redacted=str(message)
    if settings and settings.api_key:
        secret=settings.api_key.get_secret_value()
        if secret: redacted=redacted.replace(secret,"[REDACTED]")
    redacted=re.sub(r"(?i)(authorization|api[_-]?key|token|password)\s*[=:]\s*[^\s,;]+",r"\1=[REDACTED]",redacted)
    redacted=re.sub(r"://([^:/\s]+):([^@/\s]+)@",r"://\1:[REDACTED]@",redacted)
    return redacted[:1000]
