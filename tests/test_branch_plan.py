import pytest

from src.branch.addressing import build_branch_plan


def test_branch_1():
    b = build_branch_plan(1)

    assert b.name == "BRANCH-1"
    assert b.hostname == "FW-BRANCH-1"
    assert b.lan_prefix == "10.0.0.0/24"
    assert b.loopback_prefix == "172.31.255.1/32"
    assert b.vpn1_prefix == "169.255.1.0/30"
    assert b.vpn2_prefix == "169.255.1.4/30"


def test_branch_2():
    b = build_branch_plan(2)

    assert b.name == "BRANCH-2"
    assert b.hostname == "FW-BRANCH-2"
    assert b.lan_prefix == "10.0.1.0/24"
    assert b.loopback_prefix == "172.31.255.2/32"
    assert b.vpn1_prefix == "169.255.2.0/30"
    assert b.vpn2_prefix == "169.255.2.4/30"


def test_invalid_branch_id():
    with pytest.raises(ValueError):
        build_branch_plan(0)
