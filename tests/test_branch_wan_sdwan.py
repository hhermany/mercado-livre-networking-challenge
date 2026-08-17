from src.branch.configuration import generate_fortigate_branch_config
from src.branch.models import (
    BranchWANInput,
    IPsecPhase1Input,
    IPsecPhase2Input,
)


def build_config():
    return generate_fortigate_branch_config(
        branch_id=2,
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


def test_branch_has_wan_internet_zone():
    config = build_config()

    assert 'edit "WAN-INTERNET"' in config
    assert 'set interface "port2"' in config
    assert "set gateway 100.64.0.1" in config
    assert 'set interface "port3"' in config
    assert "set gateway 100.100.0.1" in config


def test_branch_has_separate_underlay_and_overlay_members():
    config = build_config()

    assert '''edit 1
            set interface "port2"
            set zone "WAN-INTERNET"
            set gateway 100.64.0.1''' in config

    assert '''edit 2
            set interface "port3"
            set zone "WAN-INTERNET"
            set gateway 100.100.0.1''' in config

    assert '''edit 3
            set interface "VPN1-PA-DC"
            set zone "VPN-DC"''' in config

    assert '''edit 4
            set interface "VPN2-PA-DC"
            set zone "VPN-DC"''' in config


def test_branch_has_internet_sla():
    config = build_config()

    assert 'edit "SLA_INTERNET"' in config
    assert 'set server "8.8.8.8"' in config
    assert "set probe-timeout 500" in config
    assert "set members 1 2" in config
    assert "set latency-threshold 150" in config
    assert "set jitter-threshold 30" in config
    assert "set packetloss-threshold 5" in config


def test_dc_sla_uses_overlay_members():
    config = build_config()

    start = config.index('edit "SLA_DC"')
    end = config.index('edit "SLA_INTERNET"')

    sla_dc = config[start:end]

    assert "set members 3 4" in sla_dc


def test_branch_has_default_route_via_wan_zone():
    config = build_config()

    assert "config router static" in config
    assert 'set sdwan-zone "WAN-INTERNET"' in config


def test_sdwan_services_separate_dc_and_internet():
    config = build_config()

    assert 'set name "TO-DC"' in config
    assert 'set dst "NET-DC"' in config
    assert "set priority-members 3 4" in config

    assert 'set name "TO-INTERNET"' in config
    assert 'edit "SLA_INTERNET"' in config
    assert "set priority-members 1 2" in config


def test_branch_defines_dc_network_object():
    config = build_config()

    assert 'edit "NET-DC"' in config
    assert "set subnet 10.255.255.0 255.255.255.0" in config
