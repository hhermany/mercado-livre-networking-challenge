import pytest

from src.branch.paloalto_cleanup import (
    generate_paloalto_branch_cleanup,
)


def test_generates_branch_2_cleanup():
    config = generate_paloalto_branch_cleanup(2)

    assert (
        "delete network virtual-router default protocol bgp "
        "peer-group IBGP-SDWAN peer FG-BRANCH-2-VPN1"
    ) in config

    assert (
        "delete network virtual-router default protocol bgp "
        "peer-group IBGP-SDWAN peer FG-BRANCH-2-VPN2"
    ) in config

    assert (
        "delete network virtual-router default interface tunnel.3"
        in config
    )

    assert (
        "delete network virtual-router default interface tunnel.4"
        in config
    )

    assert (
        "delete zone FILIAIS network layer3 tunnel.3"
        in config
    )

    assert (
        "delete zone FILIAIS network layer3 tunnel.4"
        in config
    )

    assert (
        "delete network tunnel ipsec BRANCH-2-VPN1"
        in config
    )

    assert (
        "delete network tunnel ipsec BRANCH-2-VPN2"
        in config
    )

    assert (
        "delete network ike gateway BRANCH-2-VPN1"
        in config
    )

    assert (
        "delete network ike gateway BRANCH-2-VPN2"
        in config
    )

    assert (
        "delete network interface tunnel units tunnel.3"
        in config
    )

    assert (
        "delete network interface tunnel units tunnel.4"
        in config
    )


def test_generates_branch_3_cleanup():
    config = generate_paloalto_branch_cleanup(3)

    assert "FG-BRANCH-3-VPN1" in config
    assert "FG-BRANCH-3-VPN2" in config
    assert "tunnel.5" in config
    assert "tunnel.6" in config
    assert "BRANCH-3-VPN1" in config
    assert "BRANCH-3-VPN2" in config


def test_never_deletes_shared_objects():
    config = generate_paloalto_branch_cleanup(2)

    forbidden = (
        "delete zone FILIAIS\n",
        "delete network virtual-router default\n",
        "delete network ike crypto-profiles",
        "delete network ipsec crypto-profiles",
        "delete network profiles interface-management-profile TUNNEL-MGMT",
        "delete network virtual-router default protocol bgp peer-group IBGP-SDWAN\n",
    )

    for command in forbidden:
        assert command not in f"{config}\n"


def test_golden_branch_cannot_be_destroyed():
    with pytest.raises(
        ValueError,
        match="golden",
    ):
        generate_paloalto_branch_cleanup(1)


def test_invalid_branch_is_rejected():
    with pytest.raises(ValueError):
        generate_paloalto_branch_cleanup(0)
