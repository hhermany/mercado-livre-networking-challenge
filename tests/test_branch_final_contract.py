from src.branch.addressing import build_branch_plan
from src.branch.configuration import generate_fortigate_branch_config
from src.branch.models import (
    BranchWANInput,
    IPsecPhase1Input,
    IPsecPhase2Input,
)


def _config(branch_id):
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


def test_final_vpn_addressing_contract():
    # BRANCH-1 e o golden e nao participa
    # da sequencia automatica.
    #
    # BRANCH-2 e a primeira branch criada
    # pelo onboarding automatico.
    b1 = build_branch_plan(1)
    b2 = build_branch_plan(2)
    b3 = build_branch_plan(3)

    assert b1.vpn1_prefix == "169.255.0.0/30"
    assert b1.vpn2_prefix == "169.255.0.4/30"

    assert b2.vpn1_prefix == "169.255.0.0/30"
    assert b2.vpn2_prefix == "169.255.0.4/30"

    assert b3.vpn1_prefix == "169.255.0.8/30"
    assert b3.vpn2_prefix == "169.255.0.12/30"


def test_branch_2_endpoint_roles():
    config = _config(2)

    # VPN1 169.255.0.0/30
    # PA = primeiro usable .1
    # FG = segundo usable .2
    assert "169.255.0.1" in config
    assert "169.255.0.2" in config

    # VPN2 169.255.0.4/30
    # PA = primeiro usable .5
    # FG = segundo usable .6
    assert "169.255.0.5" in config
    assert "169.255.0.6" in config


def test_branch_2_has_lan_dhcp():
    config = _config(2)

    assert "config system dhcp server" in config
    assert "set default-gateway 10.0.1.254" in config
    assert 'set interface "port4"' in config
    assert "set start-ip 10.0.1.1" in config
    assert "set end-ip 10.0.1.10" in config
    assert "set dns-server1 10.255.255.1" in config


def test_does_not_generate_fortilink_dhcp():
    config = _config(2)

    assert 'set interface "fortilink"' not in config
