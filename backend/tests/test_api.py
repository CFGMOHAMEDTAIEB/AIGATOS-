def test_health(client):
    assert client.get("/api/v1/health").json() == {"status": "ok"}


def test_vehicle_crud_and_duplicate_vin(client):
    base = "/api/v1/vehicles"
    payload = {"vin": "1HGCM82633A004352", "model": "AIGATO S", "hardware_version": "H1"}
    created = client.post(base, json=payload)
    assert created.status_code == 201
    vehicle = created.json()
    assert vehicle["vin"] == payload["vin"]
    assert client.post(base, json=payload).status_code == 409
    assert client.get(base).json()[0]["id"] == vehicle["id"]
    assert client.get(f'{base}/{vehicle["id"]}').status_code == 200
    patched = client.patch(f'{base}/{vehicle["id"]}', json={"model": "AIGATO X"})
    assert patched.status_code == 200
    assert patched.json()["model"] == "AIGATO X"
    assert client.patch(f'{base}/{vehicle["id"]}', json={"model": None}).status_code == 422
    assert client.delete(f'{base}/{vehicle["id"]}').status_code == 204
    assert client.get(f'{base}/{vehicle["id"]}').status_code == 404


def test_ecu_crud_and_parent_constraint(client):
    vehicles = "/api/v1/vehicles"
    ecus = "/api/v1/ecus"
    missing = client.post(ecus, json={
        "vehicle_id": "missing", "name": "BMS",
        "hardware_version": "H1", "software_version": "1.0",
    })
    assert missing.status_code == 404
    vehicle = client.post(vehicles, json={
        "vin": "1HGCM82633A004353", "model": "AIGATO S", "hardware_version": "H1",
    }).json()
    payload = {
        "vehicle_id": vehicle["id"], "name": "BMS",
        "hardware_version": "H1", "software_version": "1.0",
    }
    created = client.post(ecus, json=payload)
    assert created.status_code == 201
    ecu = created.json()
    assert client.post(ecus, json=payload).status_code == 409
    assert client.get(ecus).json()[0]["id"] == ecu["id"]
    assert client.patch(f'{ecus}/{ecu["id"]}', json={"software_version": "1.1"}).json()["software_version"] == "1.1"
    assert client.delete(f'{vehicles}/{vehicle["id"]}').status_code == 409
    assert client.delete(f'{ecus}/{ecu["id"]}').status_code == 204
    assert client.delete(f'{vehicles}/{vehicle["id"]}').status_code == 204


def test_package_and_campaign_crud(client):
    packages = "/api/v1/software-packages"
    campaigns = "/api/v1/campaigns"
    package_payload = {
        "name": "BMS", "version": "2.0", "target_hardware": "H1",
        "checksum_sha256": "a" * 64,
    }
    invalid = client.post(packages, json={**package_payload, "checksum_sha256": "bad"})
    assert invalid.status_code == 422
    created_package = client.post(packages, json=package_payload)
    assert created_package.status_code == 201
    package = created_package.json()
    assert client.post(packages, json=package_payload).status_code == 409
    assert client.get(packages).json()[0]["id"] == package["id"]
    assert client.patch(f'{packages}/{package["id"]}', json={"target_hardware": "H2"}).json()["target_hardware"] == "H2"
    assert client.post(campaigns, json={"name": "Canary 1", "software_package_id": "missing"}).status_code == 404
    created_campaign = client.post(campaigns, json={
        "name": "Canary 1", "software_package_id": package["id"], "canary_percentage": 5,
    })
    assert created_campaign.status_code == 201
    campaign = created_campaign.json()
    assert campaign["status"] == "draft"
    assert client.post(campaigns, json={
        "name": "Canary 1", "software_package_id": package["id"],
    }).status_code == 409
    assert client.get(campaigns).json()[0]["id"] == campaign["id"]
    assert client.patch(f'{campaigns}/{campaign["id"]}', json={"canary_percentage": 10}).json()["canary_percentage"] == 10
    assert client.patch(f'{campaigns}/{campaign["id"]}', json={"status": "active"}).status_code == 422
    assert client.delete(f'{packages}/{package["id"]}').status_code == 409
    assert client.delete(f'{campaigns}/{campaign["id"]}').status_code == 204
    assert client.delete(f'{packages}/{package["id"]}').status_code == 204


def test_validation_and_pagination(client):
    base = "/api/v1/vehicles"
    assert client.post(base, json={
        "vin": "short", "model": "A", "hardware_version": "H1",
    }).status_code == 422
    assert client.get(f"{base}?limit=0").status_code == 422
    for n in range(2):
        assert client.post(base, json={
            "vin": f"1HGCM82633A00{n:04d}", "model": "A", "hardware_version": "H1",
        }).status_code == 201
    assert len(client.get(f"{base}?limit=1").json()) == 1
    assert len(client.get(f"{base}?offset=1").json()) == 1
