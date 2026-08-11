from src.vpn.models import Datacenter, Site, TunnelRequest


def build_tunnel_requests(
    site: Site,
    datacenters: tuple[Datacenter, ...],
) -> tuple[TunnelRequest, ...]:
    """Generate all required VPN tunnel combinations for a site."""

    tunnels = []

    for site_wan in site.wan_links:
        for datacenter in datacenters:
            for dc_wan in datacenter.wan_links:
                tunnels.append(
                    TunnelRequest(
                        site_name=site.name,
                        site_wan=site_wan,
                        dc_name=datacenter.name,
                        dc_wan=dc_wan,
                    )
                )

    return tuple(tunnels)
