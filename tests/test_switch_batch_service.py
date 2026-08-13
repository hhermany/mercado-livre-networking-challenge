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
