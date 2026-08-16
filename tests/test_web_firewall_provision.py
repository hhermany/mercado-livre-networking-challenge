import src.web.app as web_app
from src.branch.addressing import (
    build_branch_plan,
)


class FakeProvisioner:
    def plan(self):
        return build_branch_plan(2)

    def provision(self, *args, **kwargs):
        raise AssertionError("Generate nao pode reservar no Nautobot.")


def setup_function():
    web_app.fortigate_manager.clear()
    web_app._firewall_candidates.clear()


def connected_device():
    device = web_app.fortigate_manager.upsert(
        host="172.28.255.200",
        username="admin",
        password="password",
    )

    device.hostname = "FW-BRANCH-1"
    device.status = "connected"

    return device


def candidate_payload(device_id):
    return {
        "device_id": device_id,
        "hostname": "FW-BRANCH-2",
        "wan1_ip": "100.64.0.3/24",
        "wan1_gateway": "100.64.0.1",
        "wan2_ip": "100.100.0.3/24",
        "wan2_gateway": "100.100.0.1",
        "phase1_ike_version": 2,
        "phase1_proposal": "des-sha256",
        "phase1_dh_group": 14,
        "phase1_psk": "TEST-PSK",
        "phase2_proposal": "des-sha256",
        "phase2_dh_group": 14,
    }


def test_firewall_plan_is_read_only(
    monkeypatch,
):
    monkeypatch.setattr(
        web_app,
        "BranchProvisioner",
        FakeProvisioner,
    )

    client = web_app.app.test_client()

    response = client.get("/api/firewalls/provision/plan")

    assert response.status_code == 200

    plan = response.get_json()["plan"]

    assert plan["name"] == "BRANCH-2"
    assert plan["lan_prefix"] == "10.0.1.0/24"
    assert plan["loopback_prefix"] == "172.31.255.2/32"


def test_generate_candidate_does_not_write_nautobot(
    monkeypatch,
):
    monkeypatch.setattr(
        web_app,
        "BranchProvisioner",
        FakeProvisioner,
    )

    device = connected_device()

    client = web_app.app.test_client()

    response = client.post(
        "/api/firewalls/provision/candidates",
        json=candidate_payload(device.id),
    )

    assert response.status_code == 200

    data = response.get_json()

    assert data["name"] == "BRANCH-2"
    assert data["hostname"] == "FW-BRANCH-2"

    candidate = web_app._firewall_candidates[data["candidate_id"]]

    assert 'set hostname "FW-BRANCH-2"' in candidate["fortigate_config"]

    assert "set ip 100.64.0.3 255.255.255.0" in candidate["fortigate_config"]

    assert "set ip 100.100.0.3 255.255.255.0" in candidate["fortigate_config"]

    assert candidate["paloalto_config"]


def test_custom_hostname_is_rendered(
    monkeypatch,
):
    monkeypatch.setattr(
        web_app,
        "BranchProvisioner",
        FakeProvisioner,
    )

    device = connected_device()

    payload = candidate_payload(device.id)

    payload["hostname"] = "FG-POA-002"

    response = web_app.app.test_client().post(
        "/api/firewalls/provision/candidates",
        json=payload,
    )

    assert response.status_code == 200

    data = response.get_json()

    candidate = web_app._firewall_candidates[data["candidate_id"]]

    assert data["hostname"] == "FG-POA-002"

    assert 'set hostname "FG-POA-002"' in candidate["fortigate_config"]


def test_candidate_view_hides_paloalto(
    monkeypatch,
):
    monkeypatch.setattr(
        web_app,
        "BranchProvisioner",
        FakeProvisioner,
    )

    device = connected_device()

    client = web_app.app.test_client()

    created = client.post(
        "/api/firewalls/provision/candidates",
        json=candidate_payload(device.id),
    ).get_json()

    response = client.get(
        "/api/firewalls/provision/candidates/" + created["candidate_id"]
    )

    assert response.status_code == 200

    candidate = response.get_json()["candidate"]

    assert "config" in candidate
    assert "paloalto_config" not in candidate


def test_candidate_download(
    monkeypatch,
):
    monkeypatch.setattr(
        web_app,
        "BranchProvisioner",
        FakeProvisioner,
    )

    device = connected_device()

    client = web_app.app.test_client()

    created = client.post(
        "/api/firewalls/provision/candidates",
        json=candidate_payload(device.id),
    ).get_json()

    response = client.get(
        "/api/firewalls/provision/candidates/" + created["candidate_id"] + "/download"
    )

    assert response.status_code == 200

    assert "attachment" in response.headers["Content-Disposition"]

    assert b"config system global" in response.data


def test_deploy_button_remains_disabled():
    html = web_app.app.test_client().get("/firewalls").get_data(as_text=True)

    assert 'id="deploy-config"' in html
    assert (
        'id="deploy-config"\n'
        '                type="button"\n'
        "                disabled" in html
    )


def test_firewall_wans_have_separate_rows():
    html = web_app.app.test_client().get("/firewalls").get_data(as_text=True)

    assert "WAN 1 / port2" in html
    assert "WAN 2 / port3" in html
    assert html.count('class="wan-row"') == 2


def test_ipsec_capabilities_intersects_fortigate_and_paloalto(
    monkeypatch,
):
    from src.vpn.capabilities import IPsecCapabilities

    class FakeFortiGateDriver:
        def __init__(self, **kwargs):
            pass

        def discover_ipsec_capabilities(self):
            return IPsecCapabilities(
                ike_versions=(1, 2),
                phase1_proposals=(
                    "des-sha1",
                    "des-sha256",
                ),
                phase1_dh_groups=(5, 14),
                phase2_proposals=(
                    "des-sha1",
                    "des-sha256",
                ),
                phase2_dh_groups=(5, 14),
            )

    class FakePaloAltoManager:
        def __init__(self, **kwargs):
            pass

        def discover_ipsec_capabilities(self):
            return IPsecCapabilities(
                ike_versions=(1, 2),
                phase1_proposals=("des-sha256",),
                phase1_dh_groups=(14,),
                phase2_proposals=("des-sha256",),
                phase2_dh_groups=(14,),
            )

    device = web_app.fortigate_manager.upsert(
        host="192.0.2.10",
        username="admin",
        password="password",
    )
    device.status = "connected"

    monkeypatch.setattr(
        "src.devices.fortigate.FortiGateDriver",
        FakeFortiGateDriver,
    )

    monkeypatch.setattr(
        web_app,
        "PaloAltoManager",
        FakePaloAltoManager,
    )

    monkeypatch.setenv(
        "PALOALTO_HOST",
        "192.0.2.20",
    )
    monkeypatch.setenv(
        "PALOALTO_USERNAME",
        "admin",
    )
    monkeypatch.setenv(
        "PALOALTO_PASSWORD",
        "password",
    )

    response = web_app.app.test_client().get(
        f"/api/firewalls/{device.id}/ipsec-capabilities"
    )

    assert response.status_code == 200

    data = response.get_json()

    assert data["success"] is True
    assert data["paloalto_ready"] is True

    assert data["compatible"]["ike_versions"] == [1, 2]
    assert data["compatible"]["phase1_proposals"] == ["des-sha256"]
    assert data["compatible"]["phase1_dh_groups"] == [14]
    assert data["compatible"]["phase2_proposals"] == ["des-sha256"]
    assert data["compatible"]["phase2_dh_groups"] == [14]


def test_firewall_ui_shows_fixed_ipsec_standard():
    html = web_app.app.test_client().get("/firewalls").get_data(as_text=True)

    assert 'id="phase1-ike"' in html
    assert 'value="2"' in html
    assert 'value="des-sha256"' in html
    assert 'value="14"' in html

    assert "Candidate bloqueado: primeiro precisamos" not in html


def test_firewall_fixed_golden_ipsec_contract():
    html = web_app.app.test_client().get("/firewalls").get_data(as_text=True)

    expected = {
        "phase1-ike": "2",
        "phase1-proposal": "des-sha256",
        "phase1-dh": "14",
        "phase2-proposal": "des-sha256",
        "phase2-dh": "14",
    }

    for element_id, value in expected.items():
        marker = f'id="{element_id}"'
        assert marker in html

        position = html.index(marker)
        snippet = html[position : position + 180]

        assert f'value="{value}"' in snippet
        assert "readonly" in snippet

    assert "Aguardando FG + PA" not in html
    assert "Candidate bloqueado:" not in html


def test_firewall_managed_devices_matches_platform_ux():
    html = web_app.app.test_client().get("/firewalls").get_data(as_text=True)

    assert "managed-device-list" in html
    assert "managed-firewall-card" in html
    assert "managed-firewall-actions" in html
    assert "firewall-select-label" in html
    assert "firewall-status-badge" in html

    assert "Selecionar" in html
    assert "Cadastrado" in html
    assert "Conectado" in html
    assert "Remover" in html

    assert 'id="manage-selected-firewalls"' in html

    assert "Gerenciar selecionados" in html


def test_firewall_has_single_selection_counter_and_management_state():
    html = web_app.app.test_client().get("/firewalls").get_data(as_text=True)

    assert html.count('id="selected-count"') == 1

    assert 'id="firewall-management-status"' in html

    assert "Nenhum FortiGate em gerenciamento." in html

    assert "Gerenciando:" in html

    assert 'id="manage-selected-firewalls"' in html


def test_firewall_ui_displays_vpn_endpoint_roles():
    html = web_app.app.test_client().get("/firewalls").get_data(as_text=True)

    assert 'id="vpn1-endpoints"' in html
    assert 'id="vpn2-endpoints"' in html

    assert "function vpnEndpoints(prefix)" in html

    assert "network + 1" in html
    assert "network + 2" in html

    assert "Palo Alto:" in html
    assert "FortiGate:" in html
