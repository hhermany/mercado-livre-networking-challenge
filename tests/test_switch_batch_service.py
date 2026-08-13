import src.switch.service as service


class FakeBatchCiscoSwitch:
    def __init__(self, **kwargs):
        pass

    def configure_interfaces(
        self,
        interfaces,
        access_vlan=None,
        voice_vlan=None,
        remove_voice_vlan=False,
        description=None,
        remove_description=False,
        admin_state=None,
    ):
        validation = {}

        for interface in interfaces:
            state_lines = [
                "Administrative Mode: static access",
                "Operational Mode: static access",
                "GigabitEthernet0/1 is up, line protocol is up",
            ]

            if access_vlan is not None:
                state_lines.append(
                    f"Access Mode VLAN: {access_vlan}"
                )

            if voice_vlan is not None:
                state_lines.append(
                    f"Voice VLAN: {voice_vlan}"
                )

            if remove_voice_vlan:
                state_lines.append(
                    "Voice VLAN: none"
                )

            if admin_state == "down":
                state_lines[-1] = (
                    "GigabitEthernet0/1 is administratively down, "
                    "line protocol is down"
                )

            running_lines = [
                f"interface {interface}",
            ]

            if description is not None:
                running_lines.append(
                    f"description {description}"
                )

            validation[interface] = {
                "interface_state": "\n".join(
                    state_lines
                ),
                "running_config": "\n".join(
                    running_lines
                ),
            }

        return (
            "",
            validation,
            "hostname SW-TEST",
        )


def fake_backup(monkeypatch, tmp_path):
    monkeypatch.setattr(
        service,
        "save_backup",
        lambda hostname, config: (
            tmp_path / "backup.cfg"
        ),
    )


def test_batch_configures_multiple_interfaces(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        service,
        "CiscoSwitch",
        FakeBatchCiscoSwitch,
    )

    fake_backup(
        monkeypatch,
        tmp_path,
    )

    result = service.provision_interfaces_batch(
        host="192.0.2.1",
        username="admin",
        password="password",
        interfaces=[
            "Gi0/1",
            "Gi0/3",
        ],
        access_vlan=10,
        voice_vlan=20,
        description="LOTE TESTE",
        admin_state="up",
    )

    assert result["success"] is True
    assert result["interfaces"] == [
        "Gi0/1",
        "Gi0/3",
    ]
    assert len(
        result["interface_results"]
    ) == 2


def test_batch_allows_remove_operations(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        service,
        "CiscoSwitch",
        FakeBatchCiscoSwitch,
    )

    fake_backup(
        monkeypatch,
        tmp_path,
    )

    result = service.provision_interfaces_batch(
        host="192.0.2.1",
        username="admin",
        password="password",
        interfaces=[
            "Gi0/1",
        ],
        remove_voice_vlan=True,
        remove_description=True,
    )

    assert result["success"] is True


def test_batch_requires_configuration():
    try:
        service.provision_interfaces_batch(
            host="192.0.2.1",
            username="admin",
            password="password",
            interfaces=[
                "Gi0/1",
            ],
        )
    except ValueError as exc:
        assert (
            "pelo menos uma configuração"
            in str(exc)
        )
    else:
        raise AssertionError(
            "ValueError esperado"
        )


def test_batch_groups_changes_by_interface(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        service,
        "CiscoSwitch",
        FakeBatchCiscoSwitch,
    )

    fake_backup(
        monkeypatch,
        tmp_path,
    )

    result = service.provision_interfaces_batch(
        host="192.0.2.1",
        username="admin",
        password="password",
        interfaces=[
            "Gi0/2",
            "Gi0/3",
        ],
        remove_description=True,
        admin_state="down",
    )

    assert result["change_groups"] == [
        {
            "interface": "Gi0/2",
            "changes": [
                "Description removida",
                "Admin Down",
            ],
        },
        {
            "interface": "Gi0/3",
            "changes": [
                "Description removida",
                "Admin Down",
            ],
        },
    ]


def test_health_marks_clean_up_interface_as_functional():
    state = """\
GigabitEthernet0/1 is up, line protocol is up (connected)
  Full-duplex, 1000Mb/s
     0 runts, 0 giants, 0 throttles
     0 input errors, 0 CRC, 0 frame, 0 overrun, 0 ignored
     100 packets output, 10000 bytes, 0 underruns
     0 output errors, 0 collisions, 0 interface resets
     0 babbles, 0 late collision, 0 deferred
     0 lost carrier, 0 no carrier, 0 pause output
     0 output buffer failures, 0 output buffers swapped out
"""

    health = service.classify_interface_health(
        state
    )

    assert health["level"] == "healthy"
    assert health["label"] == "Porta funcional"
    assert health["issues"] == []


def test_health_detects_carrier_as_physical_warning():
    state = """\
GigabitEthernet0/1 is up, line protocol is up (connected)
     2 lost carrier, 1 no carrier, 0 pause output
"""

    health = service.classify_interface_health(
        state
    )

    assert health["level"] == "danger"
    assert health["label"] == "Alerta físico/cabeamento"
    assert health["issues"][0]["category"] == "physical"
    assert "lost carrier: 2" in health["issues"][0]["detail"]
    assert "no carrier: 1" in health["issues"][0]["detail"]


def test_health_detects_crc_and_runts_as_physical_or_duplex():
    state = """\
GigabitEthernet0/1 is up, line protocol is up (connected)
     4 runts, 0 giants, 0 throttles
     4 input errors, 4 CRC, 0 frame, 0 overrun, 0 ignored
"""

    health = service.classify_interface_health(
        state
    )

    assert health["level"] == "warning"

    categories = [
        issue["category"]
        for issue in health["issues"]
    ]

    assert "physical-duplex" in categories


def test_health_classifies_buffer_errors_as_performance():
    state = """\
GigabitEthernet0/1 is up, line protocol is up (connected)
     100 packets output, 10000 bytes, 2 underruns
     3 output errors, 0 collisions, 0 interface resets
     5 output buffer failures, 0 output buffers swapped out
"""

    health = service.classify_interface_health(
        state
    )

    assert health["level"] == "warning"

    congestion = next(
        issue
        for issue in health["issues"]
        if issue["category"] == "congestion"
    )

    assert "output errors: 3" in congestion["detail"]
    assert "output buffer failures: 5" in congestion["detail"]


def test_health_flags_collisions_on_full_duplex():
    state = """\
GigabitEthernet0/1 is up, line protocol is up (connected)
  Full-duplex, 1000Mb/s
     0 output errors, 7 collisions, 0 interface resets
"""

    health = service.classify_interface_health(
        state
    )

    categories = [
        issue["category"]
        for issue in health["issues"]
    ]

    assert "duplex" in categories


def test_health_marks_admin_down_without_errors_as_neutral():
    state = """\
GigabitEthernet0/1 is administratively down, line protocol is down
     0 runts, 0 giants, 0 throttles
     0 input errors, 0 CRC, 0 frame, 0 overrun, 0 ignored
     0 output errors, 0 collisions, 0 interface resets
     0 lost carrier, 0 no carrier, 0 pause output
     0 output buffer failures, 0 output buffers swapped out
"""

    health = service.classify_interface_health(
        state
    )

    assert health["level"] == "neutral"
    assert (
        health["label"]
        == "Administrativamente desativada"
    )
