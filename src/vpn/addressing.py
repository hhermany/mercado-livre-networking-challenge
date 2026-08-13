from dataclasses import dataclass
from ipaddress import IPv4Network


@dataclass(frozen=True)
class TunnelAddressing:
    """Address information allocated for a point-to-point VPN tunnel."""

    prefix_id: str
    prefix: str
    site_ip: str
    dc_ip: str


def build_tunnel_addressing(prefix_id: str, prefix: str) -> TunnelAddressing:
    """Build tunnel endpoint addresses from an allocated IPv4 prefix."""

    network = IPv4Network(prefix)

    if network.prefixlen != 30:
        raise ValueError("VPN tunnel addressing requires a /30 prefix.")

    hosts = list(network.hosts())

    return TunnelAddressing(
        prefix_id=prefix_id,
        prefix=prefix,
        site_ip=str(hosts[1]),
        dc_ip=str(hosts[0]),
    )
