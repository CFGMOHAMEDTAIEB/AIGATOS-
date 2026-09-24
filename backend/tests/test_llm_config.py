from app.llm_config import load_llm_settings, redact_secrets


def test_llm_configuration_is_inactive_and_secret_is_masked(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "false")
    monkeypatch.setenv("LLM_PROVIDER", "nvidia")
    monkeypatch.setenv("LLM_MODEL", "future-model")
    monkeypatch.setenv("NVIDIA_API_KEY", "synthetic-test-secret")
    settings = load_llm_settings()

    assert settings.enabled is False
    assert settings.configured is False
    assert settings.api_key_variable == "NVIDIA_API_KEY"
    assert "synthetic-test-secret" not in repr(settings)
    assert redact_secrets("failure: synthetic-test-secret", settings) == "failure: [REDACTED]"
