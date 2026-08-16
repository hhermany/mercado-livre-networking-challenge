import pytest

from src.branch.addressing import build_branch_plan


def test_branch_1():
    b = build_branch_plan(1)

    assert b.name == "BRANCH-1"
    assert b.hostname == "FW-BRANCH-1"
    assert b.lan_prefix == "10.0.0.0/24"
    assert b.loopback_prefix == "172.31.255.1/32"
    assert b.vpn1_prefix == "169.255.0.0/30"
    assert b.vpn2_prefix == "169.255.0.4/30"


def test_branch_2():
    b = build_branch_plan(2)

    assert b.name == "BRANCH-2"
    assert b.hostname == "FW-BRANCH-2"
    assert b.lan_prefix == "10.0.1.0/24"
    assert b.loopback_prefix == "172.31.255.2/32"
    assert b.vpn1_prefix == "169.255.0.0/30"
    assert b.vpn2_prefix == "169.255.0.4/30"


def test_invalid_branch_id():
    with pytest.raises(ValueError):
        build_branch_plan(0)


def test_vpn_addressing_is_sequential_from_branch_2():
    branch_2 = build_branch_plan(2)
    branch_3 = build_branch_plan(3)
    branch_4 = build_branch_plan(4)

    assert branch_2.vpn1_prefix == "169.255.0.0/30"
    assert branch_2.vpn2_prefix == "169.255.0.4/30"

    assert branch_3.vpn1_prefix == "169.255.0.8/30"
    assert branch_3.vpn2_prefix == "169.255.0.12/30"

    assert branch_4.vpn1_prefix == "169.255.0.16/30"
    assert branch_4.vpn2_prefix == "169.255.0.20/30"


def test_vpn_addressing_crosses_octet_without_waste():
    # Cada branch consome dois /30 = oito enderecos.
    # BRANCH-33 ocupa .248 e .252.
    # BRANCH-34 deve continuar em 169.255.1.0.
    branch_33 = build_branch_plan(33)
    branch_34 = build_branch_plan(34)

    assert branch_33.vpn1_prefix == "169.255.0.248/30"
    assert branch_33.vpn2_prefix == "169.255.0.252/30"

    assert branch_34.vpn1_prefix == "169.255.1.0/30"
    assert branch_34.vpn2_prefix == "169.255.1.4/30"
