from src.switch.provisioning import (
    BranchVariables,
    classify_interfaces,
    render_branch_candidate,
    render_branch_sections,
)


def build_candidate():
    classification = classify_interfaces(
        [
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
                "mode": "ACCESS",
            },
            {
                "interface": "Gi0/3",
                "mode": "TRUNK",
            },
        ],
        uplink_interface="Gi0/3",
    )

    variables = BranchVariables(
        hostname="SW-BASELINE",
        management_ip="10.10.10.1",
        management_mask="255.255.255.0",
        default_gateway="10.10.10.254",
        uplink_interface="Gi0/3",
    )

    return render_branch_candidate(
        variables=variables,
        classification=classification,
    )


def test_required_baseline_commands_exist():
    config = build_candidate()

    required = (
        ("service timestamps debug datetime msec localtime show-timezone"),
        ("service timestamps log datetime msec localtime show-timezone"),
        "service password-encryption",
        "service compress-config",
        "logging buffered 102400",
        "aaa new-model",
        "aaa group server radius RAD",
        " server name RAD1",
        " server name RAD2",
        ("aaa authentication login default local"),
        ("aaa authentication dot1x default group RAD"),
        ("aaa authorization exec default local"),
        ("aaa authorization network default group RAD"),
        ("aaa authorization auth-proxy default group RAD"),
        ("aaa accounting update newinfo periodic 2880"),
        ("aaa accounting dot1x default start-stop group RAD"),
        ("aaa accounting system default start-stop group RAD"),
        ("aaa server radius dynamic-author"),
        "aaa session-id common",
        "clock timezone GMT -3 0",
        ("ip name-server 192.168.1.1 192.168.1.2"),
        ("ip domain name MercadoLivre.local"),
        ("ip dhcp snooping vlan 1-4094"),
        ("no ip dhcp snooping information option"),
        "ip dhcp snooping",
        "dot1x system-auth-control",
        "archive",
        " log config",
        "  logging enable",
        ("spanning-tree mode rapid-pvst"),
        "spanning-tree portfast default",
        ("spanning-tree portfast bpduguard default"),
        "vlan 10",
        " name DATA",
        "vlan 20",
        " name VOICE",
        "vlan 255",
        " name MANAGEMENT",
        "ip dhcp snooping trust",
        ("snmp-server community MercadoLibre007 RO"),
        ("snmp-server host 192.168.0.167 version 2c MercadoLibre007"),
        "radius server RAD1",
        "radius server RAD2",
        "line vty 0 4",
        "line vty 5 15",
        "ntp server 192.168.1.1",
        "ntp server 10.20.10.193",
    )

    for command in required:
        assert command in config


def test_vlan_666_is_not_generated():
    config = build_candidate()

    assert "vlan 666" not in config

    assert "authorize vlan 666" not in config

    assert "CRITICAL_AUTH" not in config


def test_ipdt_is_not_generated():
    config = build_candidate()

    assert "device-tracking attach-policy" not in config


def test_authentication_open_occurs_once_per_user_group():
    config = build_candidate()

    assert config.count(" authentication open") == 1


def test_user_ports_keep_dot1x_baseline():
    config = build_candidate()

    required = (
        (" description ## PORTA-DE-USUARIO ##"),
        (" switchport access vlan 10"),
        (" switchport mode access"),
        (" switchport nonegotiate"),
        (" switchport voice vlan 20"),
        (" authentication event fail action next-method"),
        (" authentication event server alive action reinitialize"),
        (" authentication host-mode multi-domain"),
        " authentication open",
        (" authentication order dot1x mab"),
        (" authentication priority dot1x mab"),
        (" authentication port-control auto"),
        (" authentication violation restrict"),
        " mab",
        " dot1x pae authenticator",
        (" dot1x timeout tx-period 15"),
        " spanning-tree portfast",
    )

    for command in required:
        assert command in config


def test_provision_port_only_receives_description():
    classification = classify_interfaces(
        [
            {
                "interface": "Gi0/0",
                "mode": "ROUTED",
                "ip_address": "172.28.255.10",
            },
            {
                "interface": "Gi0/1",
                "mode": "TRUNK",
            },
        ],
        uplink_interface="Gi0/1",
    )

    variables = BranchVariables(
        hostname="SW-PROVISION",
        management_ip="10.10.10.1",
        management_mask="255.255.255.0",
        default_gateway="10.10.10.254",
        uplink_interface="Gi0/1",
    )

    section = render_branch_sections(
        variables=variables,
        classification=classification,
    )["provision_port"]

    assert "## PORTA PARA PROVISIONAMENTO ##" in section

    assert "switchport" not in section

    assert "ip address" not in section

    assert "shutdown" not in section


def test_aaa_precedes_dot1x_interfaces():
    config = build_candidate()

    assert (
        config.index("aaa new-model")
        < config.index("aaa authentication dot1x default group RAD")
        < config.index("dot1x system-auth-control")
        < config.index("interface range Gi0/1 - 2")
        < config.index(" authentication open")
    )


def test_dhcp_snooping_uses_full_vlan_range():
    config = build_candidate()

    assert "ip dhcp snooping vlan 1-4094" in config

    assert "ip dhcp snooping vlan 10,20" not in config


def test_enable_secret_is_preserved():
    config = build_candidate()

    assert (
        "enable secret 9 "
        "$9$ZOHVgQhqPSPloU$"
        "MvZQXnEHnjUGcrwO4HVogGxwaxFx7eYK."
        "EoP2oGF5u6" in config
    )


def test_optional_platform_commands_follow_capabilities():
    from copy import deepcopy

    from src.switch.provisioning import (
        BRANCH_STANDARD_V1,
        BranchVariables,
        classify_interfaces,
        render_branch_candidate,
    )

    classification = classify_interfaces(
        [
            {
                "interface": "Gi0/0",
                "mode": "ROUTED",
                "ip_address": "172.28.255.10",
            },
            {
                "interface": "Gi0/1",
                "mode": "TRUNK",
            },
        ],
        uplink_interface="Gi0/1",
    )

    variables = BranchVariables(
        hostname="SW-CAP",
        management_ip="10.1.1.1",
        management_mask="255.255.255.0",
        default_gateway="10.1.1.254",
        uplink_interface="Gi0/1",
    )

    profile = deepcopy(BRANCH_STANDARD_V1)

    profile["unsupported_transceiver"] = False

    profile["platform_punt_keepalive"] = False

    profile["transceiver_monitoring"] = False

    config = render_branch_candidate(
        variables=variables,
        classification=classification,
        profile=profile,
    )

    assert "service unsupported-transceiver" not in config

    assert "platform punt-keepalive" not in config

    assert "transceiver type all" not in config

    profile["unsupported_transceiver"] = True

    profile["platform_punt_keepalive"] = True

    profile["transceiver_monitoring"] = True

    config = render_branch_candidate(
        variables=variables,
        classification=classification,
        profile=profile,
    )

    assert "service unsupported-transceiver" in config

    assert "platform punt-keepalive disable-kernel-core" in config

    assert "transceiver type all" in config
