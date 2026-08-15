import src.web.app as web_app
from src.switch.provisioning.preflight import (
    ProvisionCapabilities,
)


def configure_environment(
    monkeypatch,
):
    monkeypatch.setattr(
        web_app,
        "get_switch_interfaces",
        lambda **kwargs: {
            "interfaces": [
                {
                    "interface": "Gi0/0",
                    "mode": "ROUTED",
                    "ip_address": "172.28.255.10",
                },
                {
                    "interface": "Gi0/1",
                    "mode": "ACCESS",
                },
                {
                    "interface": "Gi0/2",
                    "mode": "TRUNK",
                },
            ],
            "vlan_state": "",
            "capabilities": {},
        },
    )

    monkeypatch.setattr(
        web_app,
        "get_switch_l3_interfaces",
        lambda **kwargs: {
            "interfaces": [],
        },
    )

    monkeypatch.setattr(
        web_app,
        "get_running_config",
        lambda **kwargs: "hostname OLD-SW\n",
    )


def fake_capability(
    domain_command,
):
    return ProvisionCapabilities(
        domain_command=domain_command,
        domain_syntax=(
            "ios_xe_style" if domain_command == "ip domain name" else "classic_style"
        ),
        domain_probe_output="WORD",
    )


def test_generate_uses_modern_domain_syntax(
    monkeypatch,
):
    configure_environment(monkeypatch)

    web_app.device_manager.clear()

    device = web_app.device_manager.add(
        host="192.0.2.220",
        username="admin",
        password="password",
    )

    monkeypatch.setattr(
        web_app,
        "detect_provision_capabilities",
        lambda **kwargs: fake_capability("ip domain name"),
    )

    response = web_app.app.test_client().post(
        "/api/provision/generate",
        json={
            "device_id": device.id,
            "hostname": "SW-MODERN",
            "management_ip": "10.10.10.10",
            "management_mask": "255.255.255.0",
            "default_gateway": "10.10.10.254",
            "uplink_interface": "Gi0/2",
        },
    )

    assert response.status_code == 200

    data = response.get_json()

    assert data["capabilities"]["domain_command"] == "ip domain name"

    candidate_id = data["candidate_id"]

    candidate = web_app._provision_candidates[candidate_id]["config"]

    assert "ip domain name MercadoLivre.local" in candidate

    assert "ip domain-name MercadoLivre.local" not in candidate


def test_generate_uses_classic_domain_syntax(
    monkeypatch,
):
    configure_environment(monkeypatch)

    web_app.device_manager.clear()

    device = web_app.device_manager.add(
        host="192.0.2.221",
        username="admin",
        password="password",
    )

    monkeypatch.setattr(
        web_app,
        "detect_provision_capabilities",
        lambda **kwargs: fake_capability("ip domain-name"),
    )

    response = web_app.app.test_client().post(
        "/api/provision/generate",
        json={
            "device_id": device.id,
            "hostname": "SW-CLASSIC",
            "management_ip": "10.10.20.10",
            "management_mask": "255.255.255.0",
            "default_gateway": "10.10.20.254",
            "uplink_interface": "Gi0/2",
        },
    )

    assert response.status_code == 200

    data = response.get_json()

    assert data["capabilities"]["domain_command"] == "ip domain-name"

    candidate_id = data["candidate_id"]

    candidate = web_app._provision_candidates[candidate_id]["config"]

    assert "ip domain-name MercadoLivre.local" in candidate


def test_generate_blocks_when_preflight_fails(
    monkeypatch,
):
    configure_environment(monkeypatch)

    web_app.device_manager.clear()

    device = web_app.device_manager.add(
        host="192.0.2.222",
        username="admin",
        password="password",
    )

    def fail_preflight(
        **kwargs,
    ):
        raise RuntimeError("Sintaxe de domain não suportada.")

    monkeypatch.setattr(
        web_app,
        "detect_provision_capabilities",
        fail_preflight,
    )

    response = web_app.app.test_client().post(
        "/api/provision/generate",
        json={
            "device_id": device.id,
            "hostname": "SW-FAIL",
            "management_ip": "10.10.30.10",
            "management_mask": "255.255.255.0",
            "default_gateway": "10.10.30.254",
            "uplink_interface": "Gi0/2",
        },
    )

    assert response.status_code == 400

    assert "preflight" in response.get_json()["error"].lower()
