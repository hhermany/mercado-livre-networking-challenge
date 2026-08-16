from src.ipam.nautobot import NautobotIPAMProvider
from src.vpn.models import TunnelRequest, WANLink
from src.vpn.provisioning import allocate_tunnel_topology
from src.vpn.service import VPNAddressingService


def test_allocate_multiple_tunnels_with_nautobot() -> None:
    provider = NautobotIPAMProvider()
    service = VPNAddressingService(provider)

    requests = (
        TunnelRequest(
            site_name="SITE-001",
            site_wan=WANLink(
                name="WAN-1",
                public_ip="203.0.113.10",
            ),
            dc_name="DC-01",
            dc_wan=WANLink(
                name="WAN-1",
                public_ip="198.51.100.10",
            ),
        ),
        TunnelRequest(
            site_name="SITE-001",
            site_wan=WANLink(
                name="WAN-2",
                public_ip="203.0.113.11",
            ),
            dc_name="DC-01",
            dc_wan=WANLink(
                name="WAN-1",
                public_ip="198.51.100.10",
            ),
        ),
    )

    tunnels = ()

    try:
        tunnels = allocate_tunnel_topology(
            requests=requests,
            addressing_service=service,
        )

        assert len(tunnels) == 2

        prefixes = {
            tunnel.addressing.prefix
            for tunnel in tunnels
        }

        assert len(prefixes) == 2
        assert all(
            prefix.endswith("/30")
            for prefix in prefixes
        )

    finally:
        for tunnel in tunnels:
            service.release_tunnel(tunnel.addressing.prefix_id)
