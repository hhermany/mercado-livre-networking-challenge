from src.vpn.models import TunnelRequest, WANLink
from src.vpn.provisioning import allocate_tunnel_topology
from src.vpn.service import VPNAddressingService


class FakeIPAMProvider:
    def __init__(self) -> None:
        self.counter = 0

    def allocate_prefix(self, prefix_length: int, description: str) -> dict:
        prefix = f"169.255.0.{self.counter * 4}/30"

        result = {
            "id": f"prefix-{self.counter}",
            "prefix": prefix,
        }

        self.counter += 1
        return result

    def release_prefix(self, prefix_id: str) -> None:
        pass


def test_allocate_tunnel_topology() -> None:
    requests = (
        TunnelRequest(
            site_name="SITE-001",
            site_wan=WANLink(
                name="SITE-WAN-1",
                public_ip="203.0.113.10",
            ),
            dc_name="DC-01",
            dc_wan=WANLink(
                name="DC-WAN-1",
                public_ip="198.51.100.10",
            ),
        ),
        TunnelRequest(
            site_name="SITE-001",
            site_wan=WANLink(
                name="SITE-WAN-2",
                public_ip="203.0.113.11",
            ),
            dc_name="DC-01",
            dc_wan=WANLink(
                name="DC-WAN-1",
                public_ip="198.51.100.10",
            ),
        ),
    )

    service = VPNAddressingService(FakeIPAMProvider())

    tunnels = allocate_tunnel_topology(
        requests=requests,
        addressing_service=service,
    )

    assert len(tunnels) == 2

    assert tunnels[0].addressing.prefix == "169.255.0.0/30"
    assert tunnels[0].addressing.site_ip == "169.255.0.1"
    assert tunnels[0].addressing.dc_ip == "169.255.0.2"

    assert tunnels[1].addressing.prefix == "169.255.0.4/30"
    assert tunnels[1].addressing.site_ip == "169.255.0.5"
    assert tunnels[1].addressing.dc_ip == "169.255.0.6"
