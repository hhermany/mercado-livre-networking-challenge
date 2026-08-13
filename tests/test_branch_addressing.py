import pytest

from src.vpn.branch_addressing import build_branch_addressing


def test_build_branch_1_addressing():
    branch = build_branch_addressing(
        branch_id=1,
        lan_prefix="10.0.0.0/24",
        loopback_prefix="172.31.255.1/32",
    )

    assert branch.branch_id == 1
    assert branch.name == "BRANCH-1"
    assert branch.hostname == "FW-BRANCH-1"
    assert branch.lan_prefix == "10.0.0.0/24"
    assert branch.loopback_prefix == "172.31.255.1/32"


def test_reject_invalid_lan_prefix():
    with pytest.raises(ValueError):
        build_branch_addressing(
            1,
            "10.0.0.0/25",
            "172.31.255.1/32",
        )


def test_reject_invalid_loopback_prefix():
    with pytest.raises(ValueError):
        build_branch_addressing(
            1,
            "10.0.0.0/24",
            "172.31.255.0/24",
        )
