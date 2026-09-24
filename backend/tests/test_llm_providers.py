from types import SimpleNamespace

import httpx
import pytest
from pydantic import BaseModel

from app.llm_config import LLMSettings, load_llm_settings
from app.llm_providers import (
    LLMAuthenticationError, LLMConnectTimeoutError, LLMInvalidResponseError,
    LLMModelNotFoundError, LLMPermissionError, LLMRateLimitError,
    LLMReadTimeoutError, LLMUnavailableError, LLMValidationError,
    OpenAICompatibleProvider, normalize_error,
)
from app.services.agent_llm import optional_agent_narrative


class Output(BaseModel):
    ok: bool


def _settings(**updates):
    values = dict(
        enabled=True, provider="nvidia", model="z-ai/glm-5.3",
        base_url="https://integrate.api.nvidia.com/v1", api_key="secret-test-key",
        max_retries=1,
    )
    values.update(updates)
    return LLMSettings(**values)


class FakeCompletions:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def create(self, **_):
        outcome = self.outcomes[min(self.calls, len(self.outcomes) - 1)]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=outcome))],
            usage=None,
        )


def _provider(outcomes, **settings):
    completions = FakeCompletions(outcomes)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return OpenAICompatibleProvider(_settings(**settings), client=client, sleeper=lambda _: None), completions


@pytest.mark.parametrize("status,error_type", [
    (401, LLMAuthenticationError), (403, LLMPermissionError),
    (404, LLMModelNotFoundError), (429, LLMRateLimitError),
    (500, LLMUnavailableError),
])
def test_http_errors_are_classified(status, error_type):
    error = RuntimeError("provider detail must not escape")
    error.status_code = status
    normalized = normalize_error(error, _settings())
    assert isinstance(normalized, error_type)
    assert "provider detail" not in normalized.public()["message"]


def test_timeout_errors_are_distinct():
    request = httpx.Request("POST", "https://provider.invalid/v1/chat")
    assert isinstance(normalize_error(httpx.ConnectTimeout("x", request=request), _settings()), LLMConnectTimeoutError)
    assert isinstance(normalize_error(httpx.ReadTimeout("x", request=request), _settings()), LLMReadTimeoutError)


def test_retry_policy_is_bounded_and_never_retries_403():
    forbidden = RuntimeError("forbidden"); forbidden.status_code = 403
    provider, calls = _provider([forbidden])
    with pytest.raises(LLMPermissionError): provider.generate("system", "user")
    assert calls.calls == 1

    limited = RuntimeError("limited"); limited.status_code = 429
    provider, calls = _provider([limited, '{"ok":true}'])
    assert provider.generate("system", "user").attempt_count == 2
    assert calls.calls == 2


def test_structured_output_distinguishes_invalid_json_from_schema_failure():
    provider, _ = _provider(["not-json"])
    with pytest.raises(LLMInvalidResponseError): provider.generate_structured("system", "user", Output)
    provider, _ = _provider(['{"wrong":true}'])
    with pytest.raises(LLMValidationError): provider.generate_structured("system", "user", Output)


def test_nvidia_google_urls_and_model_precedence(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvidia-secret")
    monkeypatch.setenv("LLM_PROVIDER", "nvidia")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("NVIDIA_MODEL", raising=False)
    nvidia = load_llm_settings(load_local_env=False)
    assert nvidia.base_url == "https://integrate.api.nvidia.com/v1"
    assert nvidia.model == "z-ai/glm-5.3"

    monkeypatch.setenv("LLM_PROVIDER", "google")
    monkeypatch.setenv("GOOGLE_API_KEY", "google-secret")
    monkeypatch.setenv("GOOGLE_MODEL", "gemini-configured")
    google = load_llm_settings(load_local_env=False)
    assert google.base_url == "https://generativelanguage.googleapis.com/v1beta/openai/"
    assert google.model == "gemini-configured"

    monkeypatch.setenv("LLM_MODEL", "explicit-override")
    assert load_llm_settings(load_local_env=False).model == "explicit-override"


def test_agent_llm_failure_uses_deterministic_fallback(monkeypatch):
    monkeypatch.setenv("AGENT_LLM_ENABLED", "true")
    monkeypatch.setattr("app.services.agent_llm.load_llm_settings", lambda: _settings())

    class FailingProvider:
        def generate_structured(self, *_):
            raise LLMRateLimitError("nvidia", "z-ai/glm-5.3")

    monkeypatch.setattr("app.services.agent_llm.get_provider", lambda _: FailingProvider())
    result = optional_agent_narrative("RCA", "Rank causes", {"hypothesis_count": 1}, ["evidence-1"])
    assert result.source == "DETERMINISTIC_FALLBACK"
    assert result.error_code == "LLM_RATE_LIMITED"


def test_llm_status_and_probe_endpoints_are_safe_and_write_nothing(client, monkeypatch):
    settings = _settings()
    monkeypatch.setattr("app.api.llm.load_llm_settings", lambda: settings)

    class ProbeProvider:
        def generate_structured(self, _system, _user, output_model):
            return SimpleNamespace(attempt_count=1), output_model(ok=True)

    monkeypatch.setattr("app.api.llm.get_provider", lambda _: ProbeProvider())
    before = client.get("/api/v1/ui/contexts?scope=all").json()
    status = client.get("/api/v1/llm/status")
    probe = client.post("/api/v1/llm/test")
    assert status.status_code == probe.status_code == 200
    assert status.json()["configured"] is True
    assert probe.json()["structured_output_supported"] is True
    assert probe.json()["authorized"] is True
    assert "secret-test-key" not in status.text + probe.text
    assert client.get("/api/v1/ui/contexts?scope=all").json() == before
