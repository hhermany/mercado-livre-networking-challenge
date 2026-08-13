import pytest

import src.switch.service as service


class FakeCiscoSwitch:
    def __init__(self, **kwargs):
        pass

    def configure(self, hostname=None, vlans=None):
        vlan_state = """\
VLAN Name                             Status    Ports
---- -------------------------------- --------- ----------------
10   VLAN_DADOS                       active
20   VLAN_VOZ                         active
50   VLAN_SEGURANCA                   active
100  CAPIROTO                         active
"""

        running = """
hostname SW-TEST
"""

        return "", vlan_state, running


def test_allows_hostname_only(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "CiscoSwitch", FakeCiscoSwitch)

    monkeypatch.setattr(
        service,
        "save_backup",
        lambda hostname, config: tmp_path / "backup.cfg",
    )

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

    monkeypatch.setattr(
        service,
        "save_backup",
        lambda hostname, config: tmp_path / "backup.cfg",
    )

    result = service.provision_switch(
        host="192.0.2.1",
        username="admin",
        password="password",
        hostname=None,
        vlans=[(100, "CAPIROTO")],
    )

    assert result["success"] is True


def test_rejects_empty_operation():
    with pytest.raises(ValueError):
        service.provision_switch(
            host="192.0.2.1",
            username="admin",
            password="password",
            hostname=None,
            vlans=[],
        )
