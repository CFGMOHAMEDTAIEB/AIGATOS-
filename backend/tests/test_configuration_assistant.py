from app.schemas.live import LiveSimulationDraft


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
    monkeypatch.setattr("app.api.live.generate_configuration_draft", lambda prompt: (draft, {
        "provider": "nvidia", "model": "test-model", "writes_performed": 0, "actions_executed": 0,
    }))
    response = client.post("/frontend/configuration-drafts", json={"prompt": "Créer une campagne BatteryManager pour trente véhicules"})
    assert response.status_code == 200
    assert response.json()["draft"]["fleet"]["vehicle_count"] == 30
    assert response.json()["metadata"]["writes_performed"] == 0
    assert client.get("/api/v1/ui/contexts?scope=all").json() == before


def test_llm_draft_validation_rejects_unknown_business_values():
    payload = valid_draft(); payload["injections"][0]["error_code"] = "INVENTED_ERROR"
    try:
        LiveSimulationDraft.model_validate(payload)
    except ValueError as error:
        assert "MEMORY_LAYOUT_MISMATCH" in str(error)
    else:
        raise AssertionError("An invented error_code must be rejected")
