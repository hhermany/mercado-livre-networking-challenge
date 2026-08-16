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


def test_generate_branch_2_config():
    config = build_config()

    assert "FW-BRANCH-2" in config
    assert "10.0.1.254" in config
    assert "172.31.255.2" in config

    assert "169.255.0.1" in config
    assert "169.255.0.2" in config
    assert "169.255.0.5" in config
    assert "169.255.0.6" in config

    assert "SLA_DC" in config
    assert "RM-OUT-VPN1" in config


def test_wan_configuration_is_rendered():
    config = build_config()

    assert 'edit "port2"' in config
    assert 'set alias "WAN1"' in config
    assert "set ip 100.64.0.3 255.255.255.0" in config
    assert "set allowaccess ping" in config

    assert 'edit "port3"' in config
    assert 'set alias "WAN2"' in config
    assert "set ip 100.100.0.3 255.255.255.0" in config
    assert "set allowaccess ping" in config

    # Golden real:
    # peers IPsec diretamente conectados.
    # Nao existem static defaults por WAN.
    assert "set gateway 100.64.0.1" not in config
    assert "set gateway 100.100.0.1" not in config
    assert "config router static" not in config


def test_fortigate_vpn_crypto_is_parameterized():
    config = build_config()

    assert "set ike-version 2" in config
    assert "set proposal des-sha256" in config
    assert "set dhgrp 14" in config
    assert 'set psksecret "TEST-PSK"' in config

    assert 'edit "VPN1-PA-DC"' in config
    assert 'edit "VPN2-PA-DC"' in config

    assert 'edit "VPN1-PA-DC-P2"' in config
    assert 'edit "VPN2-PA-DC-P2"' in config

    assert "set keylifeseconds 3600" in config


def test_golden_ipsec_phase2_contract():
    config = generate_fortigate_branch_config(
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
            psk="ANOTHER-PSK",
        ),
        phase2=IPsecPhase2Input(
            proposal="des-sha256",
            dh_group=14,
        ),
        dc_wan1_ip="100.64.0.1",
        dc_wan2_ip="100.100.0.1",
    )

    assert config.count("set proposal des-sha256") >= 4
    assert config.count("set dhgrp 14") >= 4


def test_vpn_interface_names_are_fixed():
    config = build_config()

    assert '"VPN1-PA-DC"' in config
    assert '"VPN2-PA-DC"' in config

    assert 'set phase1name "VPN1-PA-DC"' in config

    assert 'set phase1name "VPN2-PA-DC"' in config

    # Nome anterior da primeira VPN foi removido.
    assert '"VPN-PA-DC"' not in config

    assert 'set phase1name "VPN1-PA-DC"' in config
    assert 'set phase1name "VPN2-PA-DC"' in config


def test_custom_hostname_is_supported():
    config = generate_fortigate_branch_config(
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
        hostname="FG-POA-002",
    )

    assert 'set hostname "FG-POA-002"' in config
