import src.web.app as web_app

INTERFACES = [
    {
        "name": "Gi0/0",
        "description": "",
        "status": "connected",
        "status_label": "Up",
        "vlan": "10",
        "mode_label": "VLAN 10",
    },
    {
        "name": "Gi1/0/1",
        "description": "HOST TESTE",
        "status": "notconnect",
        "status_label": "Not Connected",
        "vlan": "1",
        "mode_label": "VLAN 1",
    },
    {
        "name": "Gi1/0/2",
        "description": "",
        "status": "disabled",
        "status_label": "Admin Down",
        "vlan": "20",
        "mode_label": "VLAN 20",
    },
]


def build_result(interface_state=""):
    return {
        "success": True,
        "missing": [],
        "backup": "backups/test.cfg",
        "configuration_output": "",
        "vlan_state": "",
        "interface_state": interface_state,
        "interface_summary": interface_state,
        "changes": [],
        "hostname": None,
    }


def configure_test_environment(monkeypatch):
    monkeypatch.setenv("SWITCH_HOST", "192.0.2.1")
    monkeypatch.setenv("SWITCH_USERNAME", "admin")
    monkeypatch.setenv("SWITCH_PASSWORD", "password")

    monkeypatch.setattr(
        web_app,
        "get_switch_interfaces",
        lambda **kwargs: {
            "interfaces": INTERFACES,
            "raw": "",
            "capabilities": {
                "stp_mode": "rapid-pvst",
                "portfast_supported": True,
                "portfast_mode": "edge",
                "portfast_enable_command": (
                    "spanning-tree portfast edge"
                ),
                "portfast_disable_command": (
                    "spanning-tree portfast disable"
                ),
            },
            "vlan_state": (
                "VLAN Name                             Status\n"
                "---- -------------------------------- ---------\n"
                "1    default                          active\n"
                "10   VLAN_DADOS                       active\n"
                "20   VLAN_VOZ                         active\n"
            ),
        },
    )


def test_get_index_is_clean(monkeypatch):
    configure_test_environment(monkeypatch)

    client = web_app.app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert b"SUCESSO" not in response.data
    assert b"ERRO" not in response.data


def test_index_shows_switch_interfaces(monkeypatch):
    configure_test_environment(monkeypatch)

    client = web_app.app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert b"Gi0/0" in response.data
    assert b"Gi1/0/1" in response.data
    assert b"Up" in response.data
    assert b"Not Connected" in response.data
    assert b"Admin Down" in response.data


def test_web_allows_access_and_voice(monkeypatch):
    configure_test_environment(monkeypatch)

    captured = {}

    def fake_provision_switch(**kwargs):
        captured.update(kwargs)
        return build_result(
            interface_state=(
                "Administrative Mode: static access\n"
                "Access Mode VLAN: 10\n"
                "Voice VLAN: 20\n"
            )
        )

    monkeypatch.setattr(
        web_app,
        "provision_switch",
        fake_provision_switch,
    )

    client = web_app.app.test_client()

    response = client.post(
        "/apply",
        data={
            "interface": "Gi0/0",
            "access_vlan": "10",
            "voice_vlan": "20",
            "admin_state": "",
        },
    )

    assert response.status_code == 200
    assert captured["interface"] == "Gi0/0"
    assert captured["access_vlan"] == 10
    assert captured["voice_vlan"] == 20
    assert captured["admin_state"] is None
    assert captured["hostname"] is None
    assert captured["vlans"] == []
    assert b"SUCESSO" in response.data


def test_web_allows_access_only(monkeypatch):
    configure_test_environment(monkeypatch)

    captured = {}

    def fake_provision_switch(**kwargs):
        captured.update(kwargs)
        return build_result(
            interface_state=(
                "Administrative Mode: static access\n"
                "Access Mode VLAN: 10\n"
            )
        )

    monkeypatch.setattr(
        web_app,
        "provision_switch",
        fake_provision_switch,
    )

    client = web_app.app.test_client()

    response = client.post(
        "/apply",
        data={
            "interface": "Gi1/0/1",
            "access_vlan": "10",
            "voice_vlan": "",
            "admin_state": "",
        },
    )

    assert response.status_code == 200
    assert captured["interface"] == "Gi1/0/1"
    assert captured["access_vlan"] == 10
    assert captured["voice_vlan"] is None
    assert b"SUCESSO" in response.data


def test_web_allows_voice_only(monkeypatch):
    configure_test_environment(monkeypatch)

    captured = {}

    def fake_provision_switch(**kwargs):
        captured.update(kwargs)
        return build_result(
            interface_state=(
                "Administrative Mode: static access\n"
                "Voice VLAN: 20\n"
            )
        )

    monkeypatch.setattr(
        web_app,
        "provision_switch",
        fake_provision_switch,
    )

    client = web_app.app.test_client()

    response = client.post(
        "/apply",
        data={
            "interface": "Gi0/0",
            "access_vlan": "",
            "voice_vlan": "20",
            "admin_state": "",
        },
    )

    assert response.status_code == 200
    assert captured["interface"] == "Gi0/0"
    assert captured["access_vlan"] is None
    assert captured["voice_vlan"] == 20
    assert b"SUCESSO" in response.data


def test_web_allows_admin_down_only(monkeypatch):
    configure_test_environment(monkeypatch)

    captured = {}

    def fake_provision_switch(**kwargs):
        captured.update(kwargs)
        return build_result(
            interface_state=(
                "GigabitEthernet1/0/1 is administratively down"
            )
        )

    monkeypatch.setattr(
        web_app,
        "provision_switch",
        fake_provision_switch,
    )

    client = web_app.app.test_client()

    response = client.post(
        "/apply",
        data={
            "interface": "Gi1/0/1",
            "access_vlan": "",
            "voice_vlan": "",
            "admin_state": "down",
        },
    )

    assert response.status_code == 200
    assert captured["interface"] == "Gi1/0/1"
    assert captured["admin_state"] == "down"
    assert captured["access_vlan"] is None
    assert captured["voice_vlan"] is None
    assert b"SUCESSO" in response.data


def test_web_allows_admin_up_only(monkeypatch):
    configure_test_environment(monkeypatch)

    captured = {}

    def fake_provision_switch(**kwargs):
        captured.update(kwargs)
        return build_result(
            interface_state=(
                "GigabitEthernet1/0/2 is down, "
                "line protocol is down"
            )
        )

    monkeypatch.setattr(
        web_app,
        "provision_switch",
        fake_provision_switch,
    )

    client = web_app.app.test_client()

    response = client.post(
        "/apply",
        data={
            "interface": "Gi1/0/2",
            "access_vlan": "",
            "voice_vlan": "",
            "admin_state": "up",
        },
    )

    assert response.status_code == 200
    assert captured["interface"] == "Gi1/0/2"
    assert captured["admin_state"] == "up"
    assert b"SUCESSO" in response.data


def test_web_rejects_unknown_interface(monkeypatch):
    configure_test_environment(monkeypatch)

    def should_not_run(**kwargs):
        raise AssertionError(
            "provision_switch não deveria ser chamado."
        )

    monkeypatch.setattr(
        web_app,
        "provision_switch",
        should_not_run,
    )

    client = web_app.app.test_client()

    response = client.post(
        "/apply",
        data={
            "interface": "Gi99/99/99",
            "access_vlan": "10",
        },
    )

    assert response.status_code == 200
    assert b"n\xc3\xa3o foi encontrada no switch" in response.data


def test_web_keeps_interface_fields_optional(monkeypatch):
    configure_test_environment(monkeypatch)

    captured = {}

    def fake_provision_switch(**kwargs):
        captured.update(kwargs)
        result = build_result()
        result["hostname"] = "SW-TEST"
        return result

    monkeypatch.setattr(
        web_app,
        "provision_switch",
        fake_provision_switch,
    )

    client = web_app.app.test_client()

    response = client.post(
        "/apply",
        data={
            "hostname": "SW-TEST",
            "interface": "",
            "access_vlan": "",
            "voice_vlan": "",
            "admin_state": "",
        },
    )

    assert response.status_code == 200
    assert captured["hostname"] == "SW-TEST"
    assert captured["interface"] is None
    assert captured["access_vlan"] is None
    assert captured["voice_vlan"] is None
    assert captured["admin_state"] is None
    assert b"SUCESSO" in response.data


def test_inventory_failure_does_not_crash_get(monkeypatch):
    configure_test_environment(monkeypatch)

    def failed_inventory(**kwargs):
        raise RuntimeError("SSH indisponível")

    monkeypatch.setattr(
        web_app,
        "get_switch_interfaces",
        failed_inventory,
    )

    client = web_app.app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert b"SSH indispon\xc3\xadvel" in response.data


def test_web_rejects_access_vlan_on_routed_interface(monkeypatch):
    configure_test_environment(monkeypatch)

    routed_interfaces = [
        {
            "name": "Gi0/0",
            "description": "UPLINK",
            "status": "connected",
            "status_label": "Up",
            "vlan": "routed",
            "mode_label": "Routed",
        }
    ]

    monkeypatch.setattr(
        web_app,
        "get_switch_interfaces",
        lambda **kwargs: {
            "interfaces": routed_interfaces,
            "raw": "",
        },
    )

    def should_not_run(**kwargs):
        raise AssertionError(
            "provision_switch não deveria ser chamado."
        )

    monkeypatch.setattr(
        web_app,
        "provision_switch",
        should_not_run,
    )

    client = web_app.app.test_client()

    response = client.post(
        "/apply",
        data={
            "interface": "Gi0/0",
            "access_vlan": "10",
        },
    )

    assert response.status_code == 200
    assert b"Layer 3" in response.data


def test_web_allows_remove_voice_vlan(monkeypatch):
    configure_test_environment(monkeypatch)

    captured = {}

    def fake_provision_switch(**kwargs):
        captured.update(kwargs)
        result = build_result(
            interface_state="Voice VLAN: none"
        )
        result["changes"] = [
            "Gi0/0: Voice VLAN removida"
        ]
        return result

    monkeypatch.setattr(
        web_app,
        "provision_switch",
        fake_provision_switch,
    )

    client = web_app.app.test_client()

    response = client.post(
        "/apply",
        data={
            "interface": "Gi0/0",
            "voice_vlan": "",
            "remove_voice_vlan": "on",
        },
    )

    assert response.status_code == 200
    assert captured["remove_voice_vlan"] is True
    assert captured["voice_vlan"] is None
    assert b"SUCESSO" in response.data


def test_web_rejects_voice_set_and_remove_together(monkeypatch):
    configure_test_environment(monkeypatch)

    client = web_app.app.test_client()

    response = client.post(
        "/apply",
        data={
            "interface": "Gi0/0",
            "voice_vlan": "20",
            "remove_voice_vlan": "on",
        },
    )

    assert response.status_code == 200
    assert b"escolha configurar" in response.data


def test_web_allows_interface_description(monkeypatch):
    configure_test_environment(monkeypatch)

    captured = {}

    def fake_provision_switch(**kwargs):
        captured.update(kwargs)
        result = build_result()
        result["changes"] = [
            "Gi0/0: Description alterada para HOST TESTE"
        ]
        return result

    monkeypatch.setattr(
        web_app,
        "provision_switch",
        fake_provision_switch,
    )

    client = web_app.app.test_client()

    response = client.post(
        "/apply",
        data={
            "interface": "Gi0/0",
            "description": "HOST TESTE",
        },
    )

    assert response.status_code == 200
    assert captured["description"] == "HOST TESTE"
    assert captured["remove_description"] is False
    assert b"SUCESSO" in response.data


def test_web_allows_remove_description(monkeypatch):
    configure_test_environment(monkeypatch)

    captured = {}

    def fake_provision_switch(**kwargs):
        captured.update(kwargs)
        result = build_result()
        result["changes"] = [
            "Gi0/0: Description removida"
        ]
        return result

    monkeypatch.setattr(
        web_app,
        "provision_switch",
        fake_provision_switch,
    )

    client = web_app.app.test_client()

    response = client.post(
        "/apply",
        data={
            "interface": "Gi0/0",
            "description": "",
            "remove_description": "on",
        },
    )

    assert response.status_code == 200
    assert captured["description"] is None
    assert captured["remove_description"] is True
    assert b"SUCESSO" in response.data


def test_web_rejects_description_and_remove_together(monkeypatch):
    configure_test_environment(monkeypatch)

    client = web_app.app.test_client()

    response = client.post(
        "/apply",
        data={
            "interface": "Gi0/0",
            "description": "HOST TESTE",
            "remove_description": "on",
        },
    )

    assert response.status_code == 200
    assert b"escolha configurar um texto" in response.data


def test_index_shows_current_vlans_before_apply(monkeypatch):
    configure_test_environment(monkeypatch)

    client = web_app.app.test_client()
    response = client.get("/")

    assert response.status_code == 200
    assert b"VLANs atuais" in response.data
    assert b"VLAN_DADOS" in response.data
    assert b"VLAN_VOZ" in response.data


def test_index_has_single_description_controls(monkeypatch):
    configure_test_environment(monkeypatch)

    client = web_app.app.test_client()
    response = client.get("/")

    html = response.data.decode()

    assert html.count('id="description"') == 1
    assert html.count('name="description"') == 1
    assert html.count('id="remove_description"') == 1
    assert html.count('name="remove_description"') == 1
    assert html.count('id="remove_voice_vlan"') == 1
    assert html.count('name="remove_voice_vlan"') == 1


def test_index_has_three_vlan_rows_without_numbered_labels(monkeypatch):
    configure_test_environment(monkeypatch)

    client = web_app.app.test_client()
    response = client.get("/")

    html = response.data.decode()

    assert html.count(">VLAN ID</label>") == 3
    assert "VLAN ID 1" not in html
    assert "VLAN ID 2" not in html
    assert "VLAN ID 3" not in html


def test_interface_inventory_precedes_port_configuration(monkeypatch):
    configure_test_environment(monkeypatch)

    client = web_app.app.test_client()
    response = client.get("/")

    html = response.data.decode()

    assert html.index("Interfaces do Equipamento") < html.index(
        "Configuração de Porta"
    )


def test_success_is_after_interface_information(monkeypatch):
    configure_test_environment(monkeypatch)

    def fake_provision_switch(**kwargs):
        result = build_result(
            interface_state=(
                "GigabitEthernet1/0/1 is up, "
                "line protocol is up\\n"
                "MTU 1500 bytes, BW 1000000 Kbit/sec\\n"
            )
        )
        result["changes"] = [
            "Gi1/0/1: Admin Up"
        ]
        return result

    monkeypatch.setattr(
        web_app,
        "provision_switch",
        fake_provision_switch,
    )

    client = web_app.app.test_client()

    response = client.post(
        "/apply",
        data={
            "interface": "Gi1/0/1",
            "admin_state": "up",
        },
    )

    html = response.data.decode()

    assert "Informações da Interface" in html
    assert html.index("Informações da Interface") < html.index(
        "SUCESSO"
    )












def test_index_shows_batch_configuration(monkeypatch):
    configure_test_environment(monkeypatch)

    client = web_app.app.test_client()
    response = client.get("/")

    assert response.status_code == 200
    assert b"Configura\xc3\xa7\xc3\xa3o de Portas" in response.data
    assert b"Intervalo de interfaces" in response.data
    assert b"Defina a configura\xc3\xa7\xc3\xa3o" in response.data
    assert b"Selecione pelo menos uma porta" in response.data


def test_batch_preview_shows_selected_interfaces(monkeypatch):
    configure_test_environment(monkeypatch)

    client = web_app.app.test_client()

    response = client.post(
        "/batch-preview",
        data={
            "batch_start_interface": "Gi0/0",
            "batch_end_interface": "Gi1/0/2",
            "batch_access_vlan": "10",
        },
    )

    assert response.status_code == 200
    assert b"Preview:" in response.data
    assert b"3 interfaces" in response.data
    assert b"Gi0/0" in response.data
    assert b"Gi1/0/1" in response.data
    assert b"Gi1/0/2" in response.data


def test_batch_preview_shows_warnings(monkeypatch):
    configure_test_environment(monkeypatch)

    client = web_app.app.test_client()

    response = client.post(
        "/batch-preview",
        data={
            "batch_start_interface": "Gi0/0",
            "batch_end_interface": "Gi1/0/1",
        },
    )

    assert response.status_code == 200
    assert b"Interface est\xc3\xa1 conectada" in response.data
    assert b"Interface possui descri\xc3\xa7\xc3\xa3o" in response.data


def test_batch_preview_does_not_apply_configuration(monkeypatch):
    configure_test_environment(monkeypatch)

    def should_not_run(**kwargs):
        raise AssertionError(
            "provision_switch nao deveria ser chamado no preview."
        )

    monkeypatch.setattr(
        web_app,
        "provision_switch",
        should_not_run,
    )

    client = web_app.app.test_client()

    response = client.post(
        "/batch-preview",
        data={
            "batch_start_interface": "Gi0/0",
            "batch_end_interface": "Gi1/0/1",
        },
    )

    assert response.status_code == 200


def test_batch_preview_rejects_reverse_range(monkeypatch):
    configure_test_environment(monkeypatch)

    client = web_app.app.test_client()

    response = client.post(
        "/batch-preview",
        data={
            "batch_start_interface": "Gi1/0/2",
            "batch_end_interface": "Gi0/0",
        },
    )

    assert response.status_code == 200
    assert b"deve aparecer antes" in response.data


def test_batch_preview_accepts_specific_checkboxes(monkeypatch):
    configure_test_environment(monkeypatch)

    client = web_app.app.test_client()

    response = client.post(
        "/batch-preview",
        data={
            "batch_interfaces": [
                "Gi0/0",
                "Gi1/0/2",
            ],
            "batch_access_vlan": "50",
            "batch_voice_vlan": "20",
        },
    )

    assert response.status_code == 200
    assert b"2 interfaces" in response.data
    assert b"Access VLAN: 50" in response.data
    assert b"Voice VLAN: 20" in response.data


def test_batch_preview_combines_range_and_checkboxes(monkeypatch):
    configure_test_environment(monkeypatch)

    client = web_app.app.test_client()

    response = client.post(
        "/batch-preview",
        data={
            "batch_interfaces": [
                "Gi1/0/2",
            ],
            "batch_start_interface": "Gi0/0",
            "batch_end_interface": "Gi1/0/1",
            "batch_description": "LOTE TESTE",
        },
    )

    assert response.status_code == 200

    html = response.data.decode()

    assert "3 interfaces" in html
    assert "Gi0/0, Gi1/0/1, Gi1/0/2" in html
    assert "Description: LOTE TESTE" in html


def test_batch_preview_deduplicates_range_and_checkbox(monkeypatch):
    configure_test_environment(monkeypatch)

    client = web_app.app.test_client()

    response = client.post(
        "/batch-preview",
        data={
            "batch_interfaces": [
                "Gi1/0/1",
            ],
            "batch_start_interface": "Gi0/0",
            "batch_end_interface": "Gi1/0/1",
        },
    )

    assert response.status_code == 200
    assert b"2 interfaces" in response.data


def test_batch_preview_shows_remove_options(monkeypatch):
    configure_test_environment(monkeypatch)

    client = web_app.app.test_client()

    response = client.post(
        "/batch-preview",
        data={
            "batch_interfaces": [
                "Gi1/0/1",
            ],
            "batch_remove_description": "on",
            "batch_remove_voice_vlan": "on",
            "batch_admin_state": "down",
        },
    )

    assert response.status_code == 200
    assert b"Remover Description" in response.data
    assert b"Remover Voice VLAN" in response.data
    assert b"Admin Down" in response.data


def test_hostname_has_independent_apply(monkeypatch):
    configure_test_environment(monkeypatch)

    captured = {}

    def fake_provision_switch(**kwargs):
        captured.update(kwargs)
        result = build_result()
        result["changes"] = [
            "Hostname: SW-NOVO"
        ]
        return result

    monkeypatch.setattr(
        web_app,
        "provision_switch",
        fake_provision_switch,
    )

    client = web_app.app.test_client()

    response = client.post(
        "/apply-hostname",
        data={
            "hostname": "SW-NOVO",
        },
    )

    assert response.status_code == 200
    assert captured["hostname"] == "SW-NOVO"


def test_vlans_have_independent_apply(monkeypatch):
    configure_test_environment(monkeypatch)

    captured = {}

    def fake_provision_switch(**kwargs):
        captured.update(kwargs)
        return build_result()

    monkeypatch.setattr(
        web_app,
        "provision_switch",
        fake_provision_switch,
    )

    client = web_app.app.test_client()

    response = client.post(
        "/apply-vlans",
        data={
            "vlan1_id": "50",
            "vlan1_name": "SEGURANCA",
        },
    )

    assert response.status_code == 200
    assert captured["vlans"] == [
        (50, "SEGURANCA"),
    ]


def test_ports_apply_multiple_interfaces(monkeypatch):
    configure_test_environment(monkeypatch)

    captured = {}

    def fake_batch(**kwargs):
        captured.update(kwargs)

        return {
            "success": True,
            "missing": [],
            "changes": [
                "Gi0/0: Access VLAN 50",
                "Gi1/0/2: Access VLAN 50",
            ],
            "backup": "backups/test.cfg",
            "interface_results": {},
            "interfaces": kwargs[
                "interfaces"
            ],
        }

    monkeypatch.setattr(
        web_app,
        "provision_interfaces_batch",
        fake_batch,
    )

    client = web_app.app.test_client()

    response = client.post(
        "/apply-ports",
        data={
            "interfaces": [
                "Gi0/0",
                "Gi1/0/2",
            ],
            "access_vlan": "50",
        },
    )

    assert response.status_code == 200

    assert captured["interfaces"] == [
        "Gi0/0",
        "Gi1/0/2",
    ]

    assert captured["access_vlan"] == 50


def test_ports_apply_combines_range_and_checkboxes(monkeypatch):
    configure_test_environment(monkeypatch)

    captured = {}

    def fake_batch(**kwargs):
        captured.update(kwargs)

        return {
            "success": True,
            "missing": [],
            "changes": [],
            "backup": "backups/test.cfg",
            "interface_results": {},
            "interfaces": kwargs[
                "interfaces"
            ],
        }

    monkeypatch.setattr(
        web_app,
        "provision_interfaces_batch",
        fake_batch,
    )

    client = web_app.app.test_client()

    response = client.post(
        "/apply-ports",
        data={
            "interfaces": [
                "Gi1/0/2",
            ],
            "range_start": "Gi0/0",
            "range_end": "Gi1/0/1",
            "description": "LOTE",
        },
    )

    assert response.status_code == 200

    assert captured["interfaces"] == [
        "Gi0/0",
        "Gi1/0/1",
        "Gi1/0/2",
    ]


def test_index_has_one_port_configuration_area(
    monkeypatch,
):
    configure_test_environment(
        monkeypatch
    )

    client = web_app.app.test_client()
    response = client.get("/")

    html = response.data.decode()

    assert html.count(
        "<h2>Configuração de Portas</h2>"
    ) == 1

    assert (
        "Visualizar Alterações"
        not in html
    )

    assert "Selecione pelo menos uma porta" in html


def test_batch_success_groups_changes_by_interface(
    monkeypatch,
):
    configure_test_environment(
        monkeypatch
    )

    def fake_batch(**kwargs):
        return {
            "success": True,
            "missing": [],
            "changes": [
                "Gi0/0: Description removida",
                "Gi0/0: Admin Down",
                "Gi1/0/1: Description removida",
                "Gi1/0/1: Admin Down",
            ],
            "change_groups": [
                {
                    "interface": "Gi0/0",
                    "changes": [
                        "Description removida",
                        "Admin Down",
                    ],
                },
                {
                    "interface": "Gi1/0/1",
                    "changes": [
                        "Description removida",
                        "Admin Down",
                    ],
                },
            ],
            "backup": "backups/test.cfg",
            "interface_results": {},
            "interfaces": kwargs["interfaces"],
        }

    monkeypatch.setattr(
        web_app,
        "provision_interfaces_batch",
        fake_batch,
    )

    client = web_app.app.test_client()

    response = client.post(
        "/apply-ports",
        data={
            "interfaces": [
                "Gi0/0",
                "Gi1/0/1",
            ],
            "remove_description": "on",
            "admin_state": "down",
        },
    )

    html = response.data.decode()

    assert response.status_code == 200
    assert "Gi0/0" in html
    assert "Gi1/0/1" in html
    assert "Description removida" in html
    assert "Admin Down" in html
    assert html.count("Description removida") == 2


def test_interface_health_uses_descriptive_status_not_ok_badge(
    monkeypatch,
):
    configure_test_environment(
        monkeypatch
    )

    def fake_batch(**kwargs):
        return {
            "success": True,
            "missing": [],
            "changes": [
                "Gi0/0: Admin Up",
            ],
            "change_groups": [
                {
                    "interface": "Gi0/0",
                    "changes": [
                        "Admin Up",
                    ],
                },
            ],
            "backup": "backups/test.cfg",
            "interfaces": [
                "Gi0/0",
            ],
            "interface_results": {
                "Gi0/0": {
                    "success": True,
                    "missing": [],
                    "summary": (
                        "GigabitEthernet0/0 is up, "
                        "line protocol is up"
                    ),
                    "health": {
                        "level": "healthy",
                        "label": "Porta funcional",
                        "issues": [],
                    },
                },
            },
        }

    monkeypatch.setattr(
        web_app,
        "provision_interfaces_batch",
        fake_batch,
    )

    client = web_app.app.test_client()

    response = client.post(
        "/apply-ports",
        data={
            "interfaces": [
                "Gi0/0",
            ],
            "admin_state": "up",
        },
    )

    html = response.data.decode()

    assert response.status_code == 200
    assert "Porta funcional" in html
    assert ">OK<" not in html


def test_interface_health_displays_physical_alert(
    monkeypatch,
):
    configure_test_environment(
        monkeypatch
    )

    def fake_batch(**kwargs):
        return {
            "success": True,
            "missing": [],
            "changes": [
                "Gi0/0: Admin Up",
            ],
            "change_groups": [],
            "backup": "backups/test.cfg",
            "interfaces": [
                "Gi0/0",
            ],
            "interface_results": {
                "Gi0/0": {
                    "success": True,
                    "missing": [],
                    "summary": (
                        "2 lost carrier, "
                        "1 no carrier"
                    ),
                    "health": {
                        "level": "danger",
                        "label": (
                            "Alerta físico/cabeamento"
                        ),
                        "issues": [
                            {
                                "level": "danger",
                                "category": "physical",
                                "title": (
                                    "Possível problema físico "
                                    "ou de cabeamento"
                                ),
                                "detail": (
                                    "lost carrier: 2, "
                                    "no carrier: 1."
                                ),
                            },
                        ],
                    },
                },
            },
        }

    monkeypatch.setattr(
        web_app,
        "provision_interfaces_batch",
        fake_batch,
    )

    client = web_app.app.test_client()

    response = client.post(
        "/apply-ports",
        data={
            "interfaces": [
                "Gi0/0",
            ],
            "admin_state": "up",
        },
    )

    html = response.data.decode()

    assert "Alerta físico/cabeamento" in html
    assert (
        "Possível problema físico ou de cabeamento"
        in html
    )


def test_index_shows_detected_portfast_capability(
    monkeypatch,
):
    configure_test_environment(
        monkeypatch
    )

    client = web_app.app.test_client()
    response = client.get("/")

    html = response.data.decode()

    assert "PortFast" in html
    assert "Habilitar Edge" in html
    assert "Desabilitar" in html
    assert "RAPID-PVST" in html
    assert "spanning-tree portfast edge" in html


def test_ports_apply_portfast_enable(
    monkeypatch,
):
    configure_test_environment(
        monkeypatch
    )

    captured = {}

    def fake_batch(**kwargs):
        captured.update(kwargs)

        return {
            "success": True,
            "missing": [],
            "changes": [
                "Gi1/0/1: PortFast Edge habilitado",
            ],
            "change_groups": [],
            "backup": "backups/test.cfg",
            "interface_results": {},
            "interfaces": kwargs["interfaces"],
        }

    monkeypatch.setattr(
        web_app,
        "provision_interfaces_batch",
        fake_batch,
    )

    client = web_app.app.test_client()

    response = client.post(
        "/apply-ports",
        data={
            "interfaces": [
                "Gi1/0/1",
            ],
            "portfast_state": "enable",
        },
    )

    assert response.status_code == 200
    assert captured["portfast_state"] == "enable"


def test_ports_apply_portfast_disable(
    monkeypatch,
):
    configure_test_environment(
        monkeypatch
    )

    captured = {}

    def fake_batch(**kwargs):
        captured.update(kwargs)

        return {
            "success": True,
            "missing": [],
            "changes": [
                "Gi1/0/1: PortFast desabilitado",
            ],
            "change_groups": [],
            "backup": "backups/test.cfg",
            "interface_results": {},
            "interfaces": kwargs["interfaces"],
        }

    monkeypatch.setattr(
        web_app,
        "provision_interfaces_batch",
        fake_batch,
    )

    client = web_app.app.test_client()

    response = client.post(
        "/apply-ports",
        data={
            "interfaces": [
                "Gi1/0/1",
            ],
            "portfast_state": "disable",
        },
    )

    assert response.status_code == 200
    assert captured["portfast_state"] == "disable"


def test_interface_inventory_contains_port_selection(
    monkeypatch,
):
    configure_test_environment(monkeypatch)

    client = web_app.app.test_client()
    response = client.get("/")

    html = response.data.decode()

    inventory_position = html.index(
        "Interfaces do Equipamento"
    )

    port_config_position = html.index(
        "Configuração de Portas"
    )

    checkbox_position = html.index(
        'class="interface-checkbox"'
    )

    assert (
        inventory_position
        < checkbox_position
        < port_config_position
    )

    assert 'form="ports-form"' in html


def test_port_configuration_does_not_duplicate_interface_grid(
    monkeypatch,
):
    configure_test_environment(monkeypatch)

    client = web_app.app.test_client()
    response = client.get("/")

    html = response.data.decode()

    assert "interface-selector" not in html
    assert "interface-name-selector" in html
    assert "<th>Selecionar</th>" not in html
    assert 'id="apply-ports-button"' in html


def test_port_configuration_uses_two_step_workflow(
    monkeypatch,
):
    configure_test_environment(monkeypatch)

    client = web_app.app.test_client()
    response = client.get("/")

    html = response.data.decode()

    assert "Escolha as interfaces" in html
    assert "Defina a configuração" in html
    assert "Intervalo de interfaces" in html

    assert html.index(
        "Escolha as interfaces"
    ) < html.index(
        "Defina a configuração"
    )


def test_port_apply_button_starts_disabled(
    monkeypatch,
):
    configure_test_environment(monkeypatch)

    client = web_app.app.test_client()
    response = client.get("/")

    html = response.data.decode()

    assert 'id="apply-ports-button"' in html
    assert "Selecione pelo menos uma porta" in html


def test_interface_checkbox_is_next_to_interface_name(
    monkeypatch,
):
    configure_test_environment(monkeypatch)

    client = web_app.app.test_client()
    response = client.get("/")

    html = response.data.decode()

    assert "interface-name-selector" in html
    assert "<th>Selecionar</th>" not in html


def test_interface_inventory_shows_voice_vlan_column(
    monkeypatch,
):
    configure_test_environment(monkeypatch)

    client = web_app.app.test_client()
    response = client.get("/")

    html = response.data.decode()

    assert "VLAN de Voz" in html



def test_interface_inventory_shows_portfast_column(
    monkeypatch,
):
    configure_test_environment(monkeypatch)

    client = web_app.app.test_client()
    response = client.get("/")

    html = response.data.decode()

    assert "<th>PortFast</th>" in html


def test_interface_description_empty_uses_double_dash(
    monkeypatch,
):
    configure_test_environment(monkeypatch)

    client = web_app.app.test_client()
    response = client.get("/")

    html = response.data.decode()

    assert "description-empty" in html
