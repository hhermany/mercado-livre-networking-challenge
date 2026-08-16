import pytest

from src.switch.cisco import (
    enrich_interfaces_with_descriptions,
    enrich_interfaces_with_etherchannel,
    enrich_interfaces_with_portfast,
    enrich_interfaces_with_switchport_details,
    enrich_interfaces_with_voice_vlan,
    normalize_interface_name,
    parse_etherchannel_members,
    parse_interface_descriptions,
    parse_interface_portfast,
    parse_interface_status,
    parse_stp_capabilities,
    parse_switchport_details,
    parse_voice_vlans,
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
    validate_interface_description("UPLINK ROUTED")


def test_stp_capabilities_detect_rapid_pvst_and_edge():
    capabilities = parse_stp_capabilities(
        "Switch is in rapid-pvst mode",
        " spanning-tree portfast edge",
    )

    assert capabilities["stp_mode"] == "rapid-pvst"
    assert capabilities["portfast_supported"] is True
    assert capabilities["portfast_mode"] == "edge"
    assert capabilities["portfast_enable_command"] == "spanning-tree portfast edge"
    assert capabilities["portfast_disable_command"] == "spanning-tree portfast disable"


def test_portfast_rejects_routed_interface():
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
            portfast_state="enable",
        )


def test_portfast_edge_rejects_trunk_interface():
    interfaces = [
        {
            "name": "Gi0/1",
            "description": "",
            "status": "connected",
            "status_label": "Up",
            "vlan": "trunk",
            "mode_label": "Trunk",
        }
    ]

    with pytest.raises(
        ValueError,
        match="trunk",
    ):
        validate_switchport_change(
            interfaces=interfaces,
            interface="Gi0/1",
            portfast_state="enable",
        )


def test_parse_voice_vlans():
    output = """\
Name: Gi0/1
Switchport: Enabled
Administrative Mode: static access
Access Mode VLAN: 10 (VLAN_DADOS)
Voice VLAN: 20 (VLAN_VOZ)

Name: Gi0/2
Switchport: Enabled
Administrative Mode: static access
Access Mode VLAN: 50 (VLAN_SEGURANCA)
Voice VLAN: none
"""

    result = parse_voice_vlans(output)

    assert result == {
        "Gi0/1": 20,
        "Gi0/2": None,
    }


def test_enrich_interfaces_with_voice_vlan():
    interfaces = [
        {
            "name": "Gi0/1",
            "description": "HOST",
            "status": "connected",
            "status_label": "Up",
            "vlan": "10",
            "mode_label": "VLAN 10",
        },
        {
            "name": "Gi0/2",
            "description": "",
            "status": "disabled",
            "status_label": "Admin Down",
            "vlan": "50",
            "mode_label": "VLAN 50",
        },
    ]

    result = enrich_interfaces_with_voice_vlan(
        interfaces,
        {
            "Gi0/1": 20,
            "Gi0/2": None,
        },
    )

    assert result[0]["voice_vlan"] == 20
    assert result[0]["voice_vlan_label"] == "VLAN 20"

    assert result[1]["voice_vlan"] is None
    assert result[1]["voice_vlan_label"] == "--"


def test_parse_interface_portfast():
    output = """\
interface GigabitEthernet0/1
 description HOST
 spanning-tree portfast edge
!
interface GigabitEthernet0/2
 switchport mode access
 spanning-tree portfast disable
!
interface GigabitEthernet0/3
 switchport mode access
!
interface GigabitEthernet1/0
 spanning-tree portfast network
"""

    result = parse_interface_portfast(output)

    assert result == {
        "GigabitEthernet0/1": "Habilitado",
        "GigabitEthernet0/2": "Desabilitado",
        "GigabitEthernet0/3": None,
        "GigabitEthernet1/0": "Network",
    }


def test_enrich_interfaces_with_portfast():
    interfaces = [
        {
            "name": "Gi0/1",
            "description": "",
            "status": "connected",
            "status_label": "Up",
            "vlan": "10",
            "mode_label": "VLAN 10",
        },
        {
            "name": "Gi0/2",
            "description": "",
            "status": "disabled",
            "status_label": "Admin Down",
            "vlan": "101",
            "mode_label": "VLAN 101",
        },
    ]

    result = enrich_interfaces_with_portfast(
        interfaces,
        {
            "Gi0/1": "Habilitado",
        },
    )

    assert result[0]["portfast"] == "Habilitado"
    assert result[0]["portfast_label"] == "Habilitado"

    assert result[1]["portfast"] is None
    assert result[1]["portfast_label"] == "--"


def test_normalize_interface_name_matches_cisco_long_and_short_names():
    assert normalize_interface_name("Gi0/1") == normalize_interface_name(
        "GigabitEthernet0/1"
    )

    assert normalize_interface_name("Gi1/0/24") == normalize_interface_name(
        "GigabitEthernet1/0/24"
    )


def test_portfast_matches_long_running_config_name_to_short_inventory_name():
    running_config = """\
interface GigabitEthernet0/1
 description HOST
 spanning-tree portfast edge
!
interface GigabitEthernet0/2
 spanning-tree portfast disable
"""

    interfaces = [
        {
            "name": "Gi0/1",
            "description": "HOST",
            "status": "connected",
            "status_label": "Up",
            "vlan": "10",
            "mode_label": "VLAN 10",
        },
        {
            "name": "Gi0/2",
            "description": "",
            "status": "disabled",
            "status_label": "Admin Down",
            "vlan": "101",
            "mode_label": "VLAN 101",
        },
    ]

    portfast = parse_interface_portfast(running_config)

    result = enrich_interfaces_with_portfast(
        interfaces,
        portfast,
    )

    assert result[0]["name"] == "Gi0/1"
    assert result[0]["portfast"] == "Habilitado"
    assert result[0]["portfast_label"] == "Habilitado"

    assert result[1]["name"] == "Gi0/2"
    assert result[1]["portfast"] == "Desabilitado"
    assert result[1]["portfast_label"] == "Desabilitado"


def test_voice_vlan_matches_long_and_short_interface_names():
    interfaces = [
        {
            "name": "Gi1/0/1",
            "description": "",
            "status": "connected",
            "status_label": "Up",
            "vlan": "10",
            "mode_label": "VLAN 10",
        },
    ]

    result = enrich_interfaces_with_voice_vlan(
        interfaces,
        {
            "GigabitEthernet1/0/1": 20,
        },
    )

    assert result[0]["voice_vlan"] == 20
    assert result[0]["voice_vlan_label"] == "VLAN 20"


def test_parse_interface_descriptions_preserves_full_description():
    output = """\
Interface                      Status         Protocol Description
Gi0/0                          up             up
Gi0/1                          up             up       ## HOST DE TESTES ##
Gi0/2                          admin down     down
Gi1/0                          up             up       UPLINK CORE PRINCIPAL
Vl10                           up             up
"""

    result = parse_interface_descriptions(output)

    assert result[normalize_interface_name("Gi0/1")] == "## HOST DE TESTES ##"

    assert result[normalize_interface_name("Gi1/0")] == "UPLINK CORE PRINCIPAL"

    assert result[normalize_interface_name("Gi0/2")] == ""


def test_enrich_interfaces_uses_description_command_as_source():
    interfaces = [
        {
            "name": "Gi0/1",
            "description": "## HOST DE TESTES",
            "status": "connected",
            "status_label": "Up",
            "vlan": "10",
            "mode_label": "VLAN 10",
        },
        {
            "name": "Gi0/2",
            "description": "",
            "status": "disabled",
            "status_label": "Admin Down",
            "vlan": "101",
            "mode_label": "VLAN 101",
        },
    ]

    descriptions = {
        normalize_interface_name("GigabitEthernet0/1"): "## HOST DE TESTES ##",
        normalize_interface_name("GigabitEthernet0/2"): "",
    }

    result = enrich_interfaces_with_descriptions(
        interfaces,
        descriptions,
    )

    assert result[0]["description"] == "## HOST DE TESTES ##"

    assert result[1]["description"] == ""


def test_parse_switchport_details_detects_trunk():
    output = """\
Name: Po1
Switchport: Enabled
Administrative Mode: trunk
Operational Mode: down
Access Mode VLAN: unassigned
Voice VLAN: none
Trunking VLANs Enabled: 10,20
Pruning VLANs Enabled: 2-1001
"""

    result = parse_switchport_details(output)

    item = result[normalize_interface_name("Po1")]

    assert item["mode"] == "trunk"
    assert item["access_vlan"] is None
    assert item["voice_vlan"] is None
    assert item["trunk_vlans"] == "10,20"


def test_enrich_interface_displays_trunk_vlans():
    interfaces = [
        {
            "name": "Po1",
            "description": "",
            "status": "notconnect",
            "status_label": "Not Connected",
            "vlan": "unassigned",
            "mode_label": "--",
        }
    ]

    details = {
        normalize_interface_name("Po1"): {
            "mode": "trunk",
            "access_vlan": None,
            "voice_vlan": None,
            "trunk_vlans": "10,20",
        }
    }

    result = enrich_interfaces_with_switchport_details(
        interfaces,
        details,
    )

    assert result[0]["mode_label"] == "TRUNK · VLANs 10,20"

    assert result[0]["switchport_mode"] == "trunk"


def test_enrich_interface_displays_access_vlan():
    interfaces = [
        {
            "name": "Gi0/1",
            "description": "",
            "status": "connected",
            "status_label": "Up",
            "vlan": "10",
            "mode_label": "VLAN 10",
        }
    ]

    details = {
        normalize_interface_name("Gi0/1"): {
            "mode": "access",
            "access_vlan": "10",
            "voice_vlan": "20",
            "trunk_vlans": None,
        }
    }

    result = enrich_interfaces_with_switchport_details(
        interfaces,
        details,
    )

    assert result[0]["mode_label"] == "ACCESS · VLAN 10"


def test_parse_etherchannel_members():
    output = """\
Group  Port-channel  Protocol    Ports
------+-------------+-----------+-----------------------------------------------
1      Po1(SD)       LACP        Gi1/2(D)    Gi1/3(D)
"""

    result = parse_etherchannel_members(output)

    assert result == {
        normalize_interface_name("Gi1/2"): "Po1",
        normalize_interface_name("Gi1/3"): "Po1",
    }


def test_enrich_interfaces_with_etherchannel():
    interfaces = [
        {
            "name": "Gi1/2",
        },
        {
            "name": "Gi1/3",
        },
        {
            "name": "Gi0/1",
        },
    ]

    members = {
        normalize_interface_name("Gi1/2"): "Po1",
        normalize_interface_name("Gi1/3"): "Po1",
    }

    result = enrich_interfaces_with_etherchannel(
        interfaces,
        members,
    )

    assert result[0]["port_channel_label"] == "Po1"
    assert result[1]["port_channel_label"] == "Po1"
    assert result[2]["port_channel_label"] == "--"
