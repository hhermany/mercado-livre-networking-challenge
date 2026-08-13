import pytest

from src.switch.cisco import (
    parse_interface_status,
    validate_interface_description,
    validate_switchport_change,
)


def test_parses_common_cisco_interface_formats():
    output = """\
Port      Name               Status       Vlan       Duplex  Speed Type
Gi0/0                        connected    routed     a-full   auto RJ45
Gi0/1     ## HOST DE TESTES  connected    10         a-full   auto RJ45
Gi1/0/1                      notconnect   1          auto     auto RJ45
Gi1/0/2                      disabled     20         auto     auto RJ45
Te1/1/1                      err-disabled 30         auto     auto SFP
"""

    result = parse_interface_status(output)

    assert result == [
        {
            "name": "Gi0/0",
            "description": "",
            "status": "connected",
            "status_label": "Up",
            "vlan": "routed",
            "mode_label": "Routed",
        },
        {
            "name": "Gi0/1",
            "description": "## HOST DE TESTES",
            "status": "connected",
            "status_label": "Up",
            "vlan": "10",
            "mode_label": "VLAN 10",
        },
        {
            "name": "Gi1/0/1",
            "description": "",
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
        {
            "name": "Te1/1/1",
            "description": "",
            "status": "err-disabled",
            "status_label": "Err-disabled",
            "vlan": "30",
            "mode_label": "VLAN 30",
        },
    ]


def test_ignores_headers_and_unrecognized_lines():
    output = """\
Port      Name               Status       Vlan       Duplex  Speed Type
----      ------------------ -----------  ---------- ------  ----- ----
something unexpected here
Gi0/1                        connected    10         a-full   auto RJ45
"""

    result = parse_interface_status(output)

    assert len(result) == 1
    assert result[0]["name"] == "Gi0/1"
    assert result[0]["vlan"] == "10"


def test_rejects_access_configuration_on_routed_port():
    interfaces = [
        {
            "name": "Gi0/0",
            "description": "",
            "status": "connected",
            "status_label": "Up",
            "vlan": "routed",
            "mode_label": "Routed",
        }
    ]

    with pytest.raises(
        ValueError,
        match="interface Layer 3",
    ):
        validate_switchport_change(
            interfaces=interfaces,
            interface="Gi0/0",
            access_vlan=10,
            voice_vlan=None,
        )


def test_rejects_remove_voice_vlan_on_routed_port():
    interfaces = [
        {
            "name": "Gi0/0",
            "description": "",
            "status": "connected",
            "status_label": "Up",
            "vlan": "routed",
            "mode_label": "Routed",
        }
    ]

    with pytest.raises(
        ValueError,
        match="Layer 3",
    ):
        validate_switchport_change(
            interfaces=interfaces,
            interface="Gi0/0",
            remove_voice_vlan=True,
        )


def test_allows_admin_change_on_routed_port():
    interfaces = [
        {
            "name": "Gi0/0",
            "description": "",
            "status": "connected",
            "status_label": "Up",
            "vlan": "routed",
            "mode_label": "Routed",
        }
    ]

    validate_switchport_change(
        interfaces=interfaces,
        interface="Gi0/0",
        access_vlan=None,
        voice_vlan=None,
    )


def test_description_validation_does_not_depend_on_switchport_mode():
    validate_interface_description(
        "UPLINK ROUTED"
    )
