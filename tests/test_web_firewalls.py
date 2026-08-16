import src.web.app as web_app


def setup_function():
    web_app.fortigate_manager.clear()


def test_firewalls_page():
    client = web_app.app.test_client()

    response = client.get("/firewalls")

    assert response.status_code == 200

    html = response.get_data(as_text=True)

    assert "Managed FortiGates" in html
    assert "Conectar / Descobrir" in html
    assert "Provision" in html
    assert "Gerar Template" in html


def test_firewall_list_starts_empty():
    client = web_app.app.test_client()

    response = client.get("/api/firewalls")

    assert response.status_code == 200
    assert response.get_json()["devices"] == []


def test_add_and_discover_firewall(
    monkeypatch,
):
    client = web_app.app.test_client()

    monkeypatch.setattr(
        web_app,
        "discover_managed_fortigate",
        lambda device: {
            "hostname": "BRANCH-2",
            "version": "FortiOS 7.2.8",
            "serial": "FGVM2",
        },
    )

    response = client.post(
        "/api/firewalls",
        json={
            "host": "192.0.2.10",
            "username": "admin",
            "password": "password",
        },
    )

    assert response.status_code == 200

    payload = response.get_json()

    assert payload["success"] is True
    assert payload["device"]["hostname"] == "BRANCH-2"
    assert payload["device"]["status"] == "connected"

    devices = client.get("/api/firewalls").get_json()["devices"]

    assert len(devices) == 1
    assert "password" not in devices[0]


def test_remove_firewall(
    monkeypatch,
):
    client = web_app.app.test_client()

    monkeypatch.setattr(
        web_app,
        "discover_managed_fortigate",
        lambda device: {
            "hostname": "BRANCH-2",
            "version": "FortiOS",
            "serial": "FGVM2",
        },
    )

    created = client.post(
        "/api/firewalls",
        json={
            "host": "192.0.2.10",
            "username": "admin",
            "password": "password",
        },
    ).get_json()

    device_id = created["device"]["id"]

    response = client.delete(f"/api/firewalls/{device_id}")

    assert response.status_code == 200

    assert client.get("/api/firewalls").get_json()["devices"] == []
