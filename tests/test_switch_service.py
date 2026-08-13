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
"""

        running = """
hostname SW-TEST
"""

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


def test_rejects_empty_operation():
    with pytest.raises(ValueError):
        service.provision_switch(
            host="192.0.2.1",
            username="admin",
            password="password",
            hostname=None,
            vlans=[],
        )
