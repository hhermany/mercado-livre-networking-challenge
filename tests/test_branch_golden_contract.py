from src.branch.configuration import generate_fortigate_branch_config
from src.branch.models import (
    BranchWANInput,
    IPsecPhase1Input,
    IPsecPhase2Input,
)


def _generate(branch_id):
    return generate_fortigate_branch_config(
        branch_id=branch_id,
        wan=BranchWANInput(
            wan1_ip="100.64.0.3/24",
            wan1_gateway="100.64.0.1",
            wan2_ip="100.100.0.3/24",
            wan2_gateway="100.100.0.1",
        ),
        phase1=IPsecPhase1Input(
            ike_version=2,
            proposal="des-sha256",
            dh_group=14,
            psk="TEST-PSK",
        ),
        phase2=IPsecPhase2Input(
            proposal="des-sha256",
            dh_group=14,
        ),
        dc_wan1_ip="100.64.0.1",
        dc_wan2_ip="100.100.0.1",
    )


def test_branch_2_uses_golden_ipsec_contract():
    config = _generate(2)

    assert 'edit "VPN1-PA-DC"' in config
    assert 'edit "VPN2-PA-DC"' in config

    assert config.count("set ike-version 2") >= 2
    assert config.count("set proposal des-sha256") >= 4
    assert config.count("set dhgrp 14") >= 4


def test_branch_2_uses_branch_specific_lan():
    config = _generate(2)

    assert "10.0.1.0" in config
    assert "10.0.1.254" in config

    assert "10.0.0.0/24" not in config


def test_branch_2_contains_sdwan_configuration():
    config = _generate(2)

    assert "config system sdwan" in config
    assert "VPN1-PA-DC" in config
    assert "VPN2-PA-DC" in config


def test_branch_2_contains_bgp_configuration():
    config = _generate(2)

    assert "config router bgp" in config
    assert "169.255.0.1" in config
    assert "169.255.0.5" in config


def test_branch_2_contains_firewall_policies():
    config = _generate(2)

    assert "config firewall policy" in config

    assert "BRANCH-LAN" in config or "BRANCH-2" in config


def test_branch_2_uses_correct_vpn_endpoint_roles():
    config = _generate(2)

    # BRANCH-2:
    #
    # VPN1 169.255.0.0/30
    # PA = .1
    # FG = .2
    #
    # VPN2 169.255.0.4/30
    # PA = .5
    # FG = .6

    assert "169.255.0.2" in config
    assert "169.255.0.6" in config

    assert "169.255.0.1" in config
    assert "169.255.0.5" in config


def test_branch_golden_interface_management_access():
    config = _generate(2)

    def interface_block(name):
        marker = f'edit "{name}"'
        start = config.index(marker)
        end = config.index(
            "\n    next",
            start,
        )
        return config[start:end]

    port2 = interface_block("port2")
    port3 = interface_block("port3")
    port4 = interface_block("port4")

    assert "set allowaccess ping" in port2
    assert "set allowaccess ping" in port3

    assert "set allowaccess ping https http" in port4


def test_branch_golden_bgp_uses_fast_advertisement():
    config = _generate(2)

    assert "config router bgp" in config

    assert config.count("set advertisement-interval 1") >= 2


def test_branch_golden_has_dc_to_management_policy():
    config = _generate(2)

    assert "edit 3" in config

    assert 'set name "DC-to-FG-MGMT"' in config

    assert 'set srcintf "VPN-DC"' in config

    assert 'set dstintf "LO-MGMT"' in config

    assert 'set srcaddr "DC-SERVER-1"' in config

    assert 'set service "SERVICES-MGMT"' in config

    assert "set logtraffic all" in config


def test_branch_real_golden_vpn_interfaces():
    config = _generate(2)

    def interface_block(name):
        section = config.index(
            "config system interface",
            config.index('edit "LO-MGMT"'),
        )

        marker = f'edit "{name}"'

        start = config.index(
            marker,
            section,
        )

        end = config.index(
            "\n    next",
            start,
        )

        return config[start:end]

    vpn1 = interface_block("VPN1-PA-DC")

    vpn2 = interface_block("VPN2-PA-DC")

    assert 'set vdom "root"' in vpn1

    assert "set ip 169.255.0.2 255.255.255.255" in vpn1

    assert "set allowaccess ping https" in vpn1

    assert "set type tunnel" in vpn1

    assert "set remote-ip 169.255.0.1 255.255.255.252" in vpn1

    assert 'set interface "port2"' in vpn1

    assert "set ip 169.255.0.6 255.255.255.255" in vpn2

    assert "set remote-ip 169.255.0.5 255.255.255.252" in vpn2

    assert "set allowaccess ping https" in vpn2

    assert "set type tunnel" in vpn2

    assert 'set interface "port3"' in vpn2


def test_branch_real_golden_sdwan_overlay_members():
    config = _generate(2)

    start = config.index("config system sdwan")

    section = config[start:]

    assert 'set interface "VPN1-PA-DC"' in section

    assert 'set interface "VPN2-PA-DC"' in section

    members_start = section.index("config members")

    members_end = section.index(
        "\n    end",
        members_start,
    )

    members = section[members_start:members_end]

    assert 'set interface "port2"' not in members

    assert 'set interface "port3"' not in members


def test_branch_real_golden_bgp_contract():
    config = _generate(2)

    assert "set ibgp-multipath enable" in config

    assert config.count("set advertisement-interval 1") >= 2

    assert 'set route-map-out "RM-OUT-VPN1"' in config

    assert 'set route-map-out "RM-OUT-VPN2"' in config


def test_branch_real_golden_community_lists():
    config = _generate(2)

    expected = (
        "COMM-VPN1-PREFER",
        "COMM-VPN2-PREFER",
        "COMM-VPN1-DEGRADED",
        "COMM-VPN2-DEGRADED",
    )

    for name in expected:
        assert f'edit "{name}"' in config


def test_branch_real_golden_has_no_static_default():
    config = _generate(2)

    assert "config router static" not in config or (
        "set gateway" not in config[config.find("config router static") :]
    )
