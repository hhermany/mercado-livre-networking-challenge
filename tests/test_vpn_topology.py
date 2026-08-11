from src.vpn.models import Datacenter, Site, WANLink
from src.vpn.topology import build_tunnel_requests


def test_build_tunnel_requests() -> None:
    site = Site(
        name="SITE-001",
        wan_links=(
            WANLink(name="SITE-WAN-1", public_ip="203.0.113.10"),
            WANLink(name="SITE-WAN-2", public_ip="203.0.113.11"),
            WANLink(name="SITE-WAN-3", public_ip="203.0.113.12"),
        ),
    )

    datacenters = (
        Datacenter(
            name="DC-01",
            wan_links=(
                WANLink(name="DC01-WAN-1", public_ip="198.51.100.10"),
                WANLink(name="DC01-WAN-2", public_ip="198.51.100.11"),
            ),
        ),
        Datacenter(
            name="DC-02",
            wan_links=(
                WANLink(name="DC02-WAN-1", public_ip="198.51.100.20"),
                WANLink(name="DC02-WAN-2", public_ip="198.51.100.21"),
            ),
        ),
    )

    tunnels = build_tunnel_requests(site, datacenters)

    assert len(tunnels) == 12
