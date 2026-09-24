from pydantic import SecretStr

from app.api import llm
from app.llm_config import LLMSettings, load_llm_settings
from app.llm_providers import ProviderResult


class FakeTextProvider:
    def __init__(self):
        self.call = None

    def generate_text(self, system, prompt):
        self.call = (system, prompt)
        return ProviderResult(content="Réponse de test sans appel réseau.")


def test_chat_uses_configured_provider_and_is_text_only(monkeypatch):
    settings = LLMSettings(
        enabled=True, provider="nvidia", model="test-model",
        base_url="https://example.invalid/v1", api_key=SecretStr("test-secret"),
        api_key_variable="NVIDIA_API_KEY",
    )
    provider = FakeTextProvider()
    monkeypatch.setattr(llm, "load_llm_settings", lambda: settings)
    monkeypatch.setattr(llm, "get_provider", lambda _settings: provider)

    result = llm.chat(llm.ChatRequest(prompt="Bonjour"))

    assert result.reply == "Réponse de test sans appel réseau."
    assert result.provider == "nvidia"
    assert provider.call[1] == "Bonjour"
    assert "cannot execute tools" in provider.call[0]


def test_chat_rejects_unconfigured_provider(monkeypatch):
    monkeypatch.setattr(llm, "load_llm_settings", lambda: LLMSettings(enabled=False))

    try:
        llm.chat(llm.ChatRequest(prompt="Bonjour"))
    except Exception as error:
        assert getattr(error, "status_code", None) == 503
        assert error.detail["code"] == "LLM_NOT_CONFIGURED"
    else:
        raise AssertionError("Unconfigured chat should be refused")


def test_openai_provider_can_be_selected_without_network(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-secret")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    settings = load_llm_settings(load_local_env=False)

    assert settings.configured
    assert settings.provider == "openai"
    assert settings.base_url == "https://api.openai.com/v1"


def test_ollama_cloud_provider_can_be_selected_without_network(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_API_KEY", "test-only-secret")
    monkeypatch.setenv("OLLAMA_MODEL", "test-model")
    monkeypatch.delenv("LLM_MODEL", raising=False)

    settings = load_llm_settings(load_local_env=False)

    assert settings.configured
    assert settings.provider == "ollama"
    assert settings.base_url == "https://ollama.com/v1"
