from dataclasses import dataclass


@dataclass(frozen=True)
class WANLink:
    """WAN link associated with a site or datacenter."""

    name: str
    public_ip: str


@dataclass(frozen=True)
class Site:
    """Remote site participating in the VPN topology."""

    name: str
    wan_links: tuple[WANLink, ...]


@dataclass(frozen=True)
class Datacenter:
    """Datacenter participating in the VPN topology."""

    name: str
    wan_links: tuple[WANLink, ...]


@dataclass(frozen=True)
class TunnelRequest:
    """Represents one VPN tunnel to be provisioned."""

    site_name: str
    site_wan: WANLink
    dc_name: str
    dc_wan: WANLink
