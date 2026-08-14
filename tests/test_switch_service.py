import pytest

import src.switch.service as service


class FakeCiscoSwitch:
    def __init__(self, **kwargs):
        pass

    def configure(
        self,
        hostname=None,
        vlans=None,
        interface=None,
        access_vlan=None,
        voice_vlan=None,
        remove_voice_vlan=False,
        description=None,
        remove_description=False,
        admin_state=None,
    ):
        vlan_state = """\
VLAN Name                             Status    Ports
---- -------------------------------- --------- ----------------
10   VLAN_DADOS                       active
20   VLAN_VOZ                         active
50   VLAN_SEGURANCA                   active
100  CAPIROTO                         active
"""

        interface_state = ""

        if interface:
            interface_state = """\
Name: Gi0/0
Switchport: Enabled
Administrative Mode: static access
Operational Mode: static access
Access Mode VLAN: 10 (VLAN_DADOS)
Voice VLAN: 20 (VLAN_VOZ)
GigabitEthernet0/0 is up, line protocol is up
"""

            if remove_voice_vlan:
                interface_state = """\
Name: Gi0/0
Switchport: Enabled
Administrative Mode: static access
Operational Mode: static access
Access Mode VLAN: 10 (VLAN_DADOS)
Voice VLAN: none
GigabitEthernet0/0 is up, line protocol is up
"""

            if admin_state == "down":
                interface_state = """\
GigabitEthernet0/0 is administratively down, line protocol is down
"""

        running_lines = [
            "hostname SW-TEST",
        ]

        if interface and description is not None:
            running_lines.extend(
                [
                    f"interface {interface}",
                    f"description {description}",
                ]
            )

        if interface and remove_description:
            running_lines.extend(
                [
                    f"interface {interface}",
                ]
            )

        running = "\n".join(running_lines)

        return "", vlan_state, interface_state, running


def fake_backup(monkeypatch, tmp_path):
    monkeypatch.setattr(
        service,
        "save_backup",
        lambda hostname, config: tmp_path / "backup.cfg",
    )


def test_allows_hostname_only(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "CiscoSwitch", FakeCiscoSwitch)
    fake_backup(monkeypatch, tmp_path)

    result = service.provision_switch(
        host="192.0.2.1",
        username="admin",
        password="password",
        hostname="SW-TEST",
        vlans=[],
    )

    assert result["success"] is True


def test_allows_single_vlan_only(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "CiscoSwitch", FakeCiscoSwitch)
    fake_backup(monkeypatch, tmp_path)

    result = service.provision_switch(
        host="192.0.2.1",
        username="admin",
        password="password",
        hostname=None,
        vlans=[(100, "CAPIROTO")],
    )

    assert result["success"] is True


def test_allows_access_and_voice_vlan(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "CiscoSwitch", FakeCiscoSwitch)
    fake_backup(monkeypatch, tmp_path)

    result = service.provision_switch(
        host="192.0.2.1",
        username="admin",
        password="password",
        interface="Gi0/0",
        access_vlan=10,
        voice_vlan=20,
    )

    assert result["success"] is True
    assert "Administrative Mode: static access" in result["interface_state"]


def test_allows_access_vlan_only(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "CiscoSwitch", FakeCiscoSwitch)
    fake_backup(monkeypatch, tmp_path)

    result = service.provision_switch(
        host="192.0.2.1",
        username="admin",
        password="password",
        interface="Gi0/0",
        access_vlan=10,
    )

    assert result["success"] is True


def test_allows_voice_vlan_only(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "CiscoSwitch", FakeCiscoSwitch)
    fake_backup(monkeypatch, tmp_path)

    result = service.provision_switch(
        host="192.0.2.1",
        username="admin",
        password="password",
        interface="Gi0/0",
        voice_vlan=20,
    )

    assert result["success"] is True


def test_requires_interface_for_access_vlan():
    with pytest.raises(
        ValueError,
        match="Informe a interface",
    ):
        service.provision_switch(
            host="192.0.2.1",
            username="admin",
            password="password",
            access_vlan=10,
        )


def test_requires_interface_for_voice_vlan():
    with pytest.raises(
        ValueError,
        match="Informe a interface",
    ):
        service.provision_switch(
            host="192.0.2.1",
            username="admin",
            password="password",
            voice_vlan=20,
        )



def test_allows_admin_down_only(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "CiscoSwitch", FakeCiscoSwitch)
    fake_backup(monkeypatch, tmp_path)

    result = service.provision_switch(
        host="192.0.2.1",
        username="admin",
        password="password",
        interface="Gi0/0",
        admin_state="down",
    )

    assert result["success"] is True


def test_allows_admin_up_only(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "CiscoSwitch", FakeCiscoSwitch)
    fake_backup(monkeypatch, tmp_path)

    result = service.provision_switch(
        host="192.0.2.1",
        username="admin",
        password="password",
        interface="Gi0/0",
        admin_state="up",
    )

    assert result["success"] is True


def test_rejects_invalid_admin_state():
    with pytest.raises(
        ValueError,
        match="Estado administrativo",
    ):
        service.provision_switch(
            host="192.0.2.1",
            username="admin",
            password="password",
            interface="Gi0/0",
            admin_state="banana",
        )


def test_allows_remove_voice_vlan(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "CiscoSwitch", FakeCiscoSwitch)
    fake_backup(monkeypatch, tmp_path)

    result = service.provision_switch(
        host="192.0.2.1",
        username="admin",
        password="password",
        interface="Gi0/0",
        remove_voice_vlan=True,
    )

    assert result["success"] is True
    assert "Gi0/0: Voice VLAN removida" in result["changes"]


def test_rejects_set_and_remove_voice_vlan_together():
    with pytest.raises(
        ValueError,
        match="não as duas opções",
    ):
        service.provision_switch(
            host="192.0.2.1",
            username="admin",
            password="password",
            interface="Gi0/0",
            voice_vlan=20,
            remove_voice_vlan=True,
        )


def test_allows_interface_description(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "CiscoSwitch", FakeCiscoSwitch)
    fake_backup(monkeypatch, tmp_path)

    result = service.provision_switch(
        host="192.0.2.1",
        username="admin",
        password="password",
        interface="Gi0/0",
        description="HOST DE TESTES",
    )

    assert result["success"] is True
    assert (
        "Gi0/0: Description alterada para HOST DE TESTES"
        in result["changes"]
    )


def test_allows_remove_interface_description(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "CiscoSwitch", FakeCiscoSwitch)
    fake_backup(monkeypatch, tmp_path)

    result = service.provision_switch(
        host="192.0.2.1",
        username="admin",
        password="password",
        interface="Gi0/0",
        remove_description=True,
    )

    assert result["success"] is True
    assert "Gi0/0: Description removida" in result["changes"]


def test_rejects_description_and_remove_together():
    with pytest.raises(
        ValueError,
        match="não as duas opções",
    ):
        service.provision_switch(
            host="192.0.2.1",
            username="admin",
            password="password",
            interface="Gi0/0",
            description="HOST TESTE",
            remove_description=True,
        )


@pytest.mark.parametrize(
    "description",
    [
        "HOST TESTE",
        "HOST-DE-TESTE",
        "HOST_TESTE",
        "HOST/TESTE",
        "## HOST TESTE ##",
        "HOST (TESTE)",
        "HOST: TESTE",
        "HOST TESTE - ANDAR 2 / SALA 10",
        "X" * 80,
    ],
)
def test_accepts_tested_description_formats(description):
    service.validate_interface_description(description)


@pytest.mark.parametrize(
    "description",
    [
        "X" * 81,
        "HOST@TESTE",
        "HOST;TESTE",
        "HOST|TESTE",
    ],
)
def test_rejects_unvalidated_description_formats(description):
    with pytest.raises(
        ValueError,
        match="Descrição inválida",
    ):
        service.validate_interface_description(description)

def test_rejects_empty_operation():
    with pytest.raises(ValueError):
        service.provision_switch(
            host="192.0.2.1",
            username="admin",
            password="password",
            hostname=None,
            vlans=[],
        )


def test_summarizes_interface_state():
    raw = """\
Name: Gi0/1
Switchport: Enabled
Administrative Mode: static access
Operational Mode: static access
Access Mode VLAN: 10 (VLAN_DADOS)
Trunking Native Mode VLAN: 1 (default)
Administrative Native VLAN tagging: enabled
Voice VLAN: 20 (VLAN_VOZ)
Protected: false

GigabitEthernet0/1 is up, line protocol is up (connected)
  MTU 1500 bytes, BW 1000000 Kbit/sec, DLY 10 usec,
     0 runts, 0 giants, 0 throttles
     0 input errors, 0 CRC, 0 frame, 0 overrun, 0 ignored
     100 packets output, 10000 bytes, 0 underruns
     0 output errors, 0 collisions, 0 interface resets
     0 unknown protocol drops
     0 babbles, 0 late collision, 0 deferred
     0 lost carrier, 0 no carrier, 0 pause output
     0 output buffer failures, 0 output buffers swapped out
"""

    summary = service.summarize_interface_state(raw)

    assert "Switchport: Enabled" in summary
    assert "Administrative Mode: static access" in summary
    assert "Access Mode VLAN: 10" in summary
    assert "Voice VLAN: 20" in summary
    assert "GigabitEthernet0/1 is up" in summary
    assert "MTU 1500 bytes" in summary
    assert "input errors" in summary
    assert "output errors" in summary
    assert "Protected: false" not in summary


def test_detects_vlan_name_divergence_after_configuration(
    monkeypatch,
    tmp_path,
):
    import src.switch.service as service

    class DivergentVlanSwitch:
        def __init__(self, **kwargs):
            pass

        def configure(
            self,
            hostname=None,
            vlans=None,
            interface=None,
            access_vlan=None,
            voice_vlan=None,
            remove_voice_vlan=False,
            description=None,
            remove_description=False,
            admin_state=None,
        ):
            vlan_state = """\
VLAN Name                             Status    Ports
---- -------------------------------- --------- ----------------
10   VLAN_ERRADA                      active
20   VLAN_VOZ                         active
50   VLAN_SEGURANCA                   active
"""

            running = """\
hostname SW-TESTE1
"""

            return (
                "",
                vlan_state,
                "",
                running,
            )

    monkeypatch.setattr(
        service,
        "CiscoSwitch",
        DivergentVlanSwitch,
    )

    monkeypatch.setattr(
        service,
        "save_backup",
        lambda hostname, config: (
            tmp_path / "backup.cfg"
        ),
    )

    result = service.provision_switch(
        host="192.0.2.1",
        username="admin",
        password="password",
        hostname="SW-TESTE1",
        vlans=[
            (10, "VLAN_DADOS"),
            (20, "VLAN_VOZ"),
            (50, "VLAN_SEGURANCA"),
        ],
    )

    rendered = str(result).lower()

    assert (
        "vlan_dados" in rendered
        or "vlan 10" in rendered
        or "10" in rendered
    )

    assert (
        "missing" in result
        or "diverg" in rendered
        or result.get("success") is False
    )


def test_detects_hostname_divergence_after_configuration(
    monkeypatch,
    tmp_path,
):
    import src.switch.service as service

    class DivergentHostnameSwitch:
        def __init__(self, **kwargs):
            pass

        def configure(
            self,
            hostname=None,
            vlans=None,
            interface=None,
            access_vlan=None,
            voice_vlan=None,
            remove_voice_vlan=False,
            description=None,
            remove_description=False,
            admin_state=None,
        ):
            vlan_state = """\
VLAN Name                             Status    Ports
---- -------------------------------- --------- ----------------
10   VLAN_DADOS                       active
20   VLAN_VOZ                         active
50   VLAN_SEGURANCA                   active
"""

            running = """\
hostname SW-ERRADO
"""

            return (
                "",
                vlan_state,
                "",
                running,
            )

    monkeypatch.setattr(
        service,
        "CiscoSwitch",
        DivergentHostnameSwitch,
    )

    monkeypatch.setattr(
        service,
        "save_backup",
        lambda hostname, config: (
            tmp_path / "backup.cfg"
        ),
    )

    result = service.provision_switch(
        host="192.0.2.1",
        username="admin",
        password="password",
        hostname="SW-TESTE1",
        vlans=[
            (10, "VLAN_DADOS"),
            (20, "VLAN_VOZ"),
            (50, "VLAN_SEGURANCA"),
        ],
    )

    rendered = str(result).lower()

    assert (
        "sw-teste1" in rendered
        or "hostname" in rendered
    )

    assert (
        "missing" in result
        or "diverg" in rendered
        or result.get("success") is False
    )


def test_cisco_default_interfaces_sends_ios_default_command(
    monkeypatch,
):
    import src.switch.cisco as cisco

    commands_seen = []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(
            self,
            exc_type,
            exc_value,
            traceback,
        ):
            return False

        def send_config_set(
            self,
            commands,
            **kwargs,
        ):
            commands_seen.extend(
                commands
            )
            return "OK"

        def send_command(
            self,
            command,
            **kwargs,
        ):
            return command

    switch = cisco.CiscoSwitch(
        host="192.0.2.10",
        username="admin",
        password="password",
    )

    monkeypatch.setattr(
        switch,
        "_connect",
        lambda: FakeConnection(),
    )

    result = switch.default_interfaces(
        [
            "Gi1/1",
            "Gi1/2",
        ]
    )

    assert commands_seen == [
        "default interface Gi1/1",
        "default interface Gi1/2",
    ]

    assert (
        "Gi1/1"
        in result["validation"]
    )

    assert (
        "Gi1/2"
        in result["validation"]
    )


def test_cisco_bounce_interfaces_sends_shutdown_no_shutdown(
    monkeypatch,
):
    import src.switch.cisco as cisco

    commands_seen = []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(
            self,
            exc_type,
            exc_value,
            traceback,
        ):
            return False

        def send_config_set(
            self,
            commands,
            **kwargs,
        ):
            commands_seen.extend(
                commands
            )
            return "OK"

        def send_command(
            self,
            command,
            **kwargs,
        ):
            return command

    switch = cisco.CiscoSwitch(
        host="192.0.2.10",
        username="admin",
        password="password",
    )

    monkeypatch.setattr(
        switch,
        "_connect",
        lambda: FakeConnection(),
    )

    result = switch.bounce_interfaces(
        [
            "Gi1/1",
            "Gi1/2",
        ]
    )

    assert commands_seen == [
        "interface Gi1/1",
        "shutdown",
        "interface Gi1/2",
        "shutdown",
        "interface Gi1/1",
        "no shutdown",
        "interface Gi1/2",
        "no shutdown",
    ]

    assert (
        "Gi1/1"
        in result["validation"]
    )

    assert (
        "Gi1/2"
        in result["validation"]
    )
