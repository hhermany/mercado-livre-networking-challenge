import pytest

from src.vpn.addressing import build_tunnel_addressing


def test_build_tunnel_addressing() -> None:
    addressing = build_tunnel_addressing(
        prefix_id="test-id",
        prefix="169.255.0.0/30",
    )

    assert addressing.prefix_id == "test-id"
    assert addressing.prefix == "169.255.0.0/30"
    assert addressing.site_ip == "169.255.0.2"
    assert addressing.dc_ip == "169.255.0.1"


def test_reject_non_30_prefix() -> None:
    with pytest.raises(ValueError):
        build_tunnel_addressing(
            prefix_id="test-id",
            prefix="169.255.0.0/29",
        )
