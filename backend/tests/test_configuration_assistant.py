from app.schemas.live import LiveSimulationDraft
from app.services.configuration_assistant import ConfigurationAssistantError, generate_configuration_draft
from app.llm_config import LLMSettings
from app.llm_providers import ProviderResult


def valid_draft():
    return {
        "created_by": "operator", "seed": 42,
        "campaign": {"name": "Assistant draft", "component": "BatteryManager", "current_version": "2.3.0", "target_version": "2.6.0", "package_type": "DELTA", "package_size_mb": 128, "canary_strategy": "CONTROLLED", "failure_threshold": .2},
        "fleet": {"vehicle_count": 30, "model": "AIGATOS EV", "region": "EU-LAB", "hw_rev_a": 27, "hw_rev_b": 3, "average_battery": 80, "average_network_quality": 90, "available_storage_mb": 4096, "temperature_c": 24},
        "injections": [{"scenario": "hardware_software_incompatible", "affected_count": 3, "affected_percentage": None, "target_hardware_revision": "HW_REV_B", "error_code": "MEMORY_LAYOUT_MISMATCH", "installation_step": "MEMORY_VALIDATION", "failure_probability": 1}],
    }


def test_llm_draft_endpoint_never_writes_or_executes(client, monkeypatch):
    before = client.get("/api/v1/ui/contexts?scope=all").json()
    draft = LiveSimulationDraft.model_validate(valid_draft())
    monkeypatch.setattr("app.api.live.generate_configuration_draft", lambda prompt, current_draft=None: (draft, {
        "provider": "nvidia", "model": "test-model", "writes_performed": 0, "actions_executed": 0,
    }))
    response = client.post("/frontend/configuration-drafts", json={"prompt": "Créer une campagne BatteryManager pour trente véhicules"})
    assert response.status_code == 200
    assert response.json()["draft"]["fleet"]["vehicle_count"] == 30
    assert response.json()["metadata"]["writes_performed"] == 0
    assert client.get("/api/v1/ui/contexts?scope=all").json() == before


def test_configuration_draft_forwards_existing_values_without_writing(client, monkeypatch):
    draft = LiveSimulationDraft.model_validate(valid_draft())
    received = {}

    def fake_generate(prompt, current_draft=None):
        received["prompt"] = prompt
        received["current_draft"] = current_draft
        return draft, {"provider": "ollama", "model": "test-only", "writes_performed": 0, "actions_executed": 0}

    monkeypatch.setattr("app.api.live.generate_configuration_draft", fake_generate)
    response = client.post("/frontend/configuration-drafts", json={
        "prompt": "Teste uniquement la température à 38 °C",
        "current_draft": valid_draft(),
    })

    assert response.status_code == 200
    assert received["current_draft"].fleet.temperature_c == 24
    assert response.json()["metadata"]["writes_performed"] == 0


def test_temperature_only_edit_preserves_every_other_field(monkeypatch):
    current = LiveSimulationDraft.model_validate(valid_draft())
    expected = current.model_copy(deep=True)
    expected.fleet.temperature_c = 38

    class FakeProvider:
        def generate_structured(self, *_args):
            return ProviderResult(content="{}"), expected

    monkeypatch.setattr("app.services.configuration_assistant.load_llm_settings", lambda: LLMSettings(
        enabled=True, provider="nvidia", model="test", base_url="https://example.invalid/v1",
        api_key="test-key",
    ))
    monkeypatch.setattr("app.services.configuration_assistant.get_provider", lambda _settings: FakeProvider())

    result, metadata = generate_configuration_draft("Teste uniquement la température à 38 °C", current)

    assert result.fleet.temperature_c == 38
    assert result.campaign == current.campaign
    assert result.injections == current.injections
    assert metadata["writes_performed"] == 0


def test_temperature_only_edit_rejects_unrequested_changes(monkeypatch):
    current = LiveSimulationDraft.model_validate(valid_draft())
    unexpected = current.model_copy(deep=True)
    unexpected.fleet.temperature_c = 38
    unexpected.campaign.name = "Unexpected rename"

    class FakeProvider:
        def generate_structured(self, *_args):
            return ProviderResult(content="{}"), unexpected

    monkeypatch.setattr("app.services.configuration_assistant.load_llm_settings", lambda: LLMSettings(
        enabled=True, provider="nvidia", model="test", base_url="https://example.invalid/v1",
        api_key="test-key",
    ))
    monkeypatch.setattr("app.services.configuration_assistant.get_provider", lambda _settings: FakeProvider())

    try:
        generate_configuration_draft("Teste uniquement la température à 38 °C", current)
    except ConfigurationAssistantError as error:
        assert "modifié d’autres champs" in str(error)
    else:
        raise AssertionError("A temperature-only request must not modify other fields")


def test_llm_draft_validation_rejects_unknown_business_values():
    payload = valid_draft(); payload["injections"][0]["error_code"] = "INVENTED_ERROR"
    try:
        LiveSimulationDraft.model_validate(payload)
    except ValueError as error:
        assert "MEMORY_LAYOUT_MISMATCH" in str(error)
    else:
        raise AssertionError("An invented error_code must be rejected")
