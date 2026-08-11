from src.vpn.models import Datacenter, Site, TunnelRequest, WANLink


def test_vpn_topology_models() -> None:
    site_wan = WANLink(
        name="SITE-WAN-1",
        public_ip="203.0.113.10",
    )

    dc_wan = WANLink(
        name="DC-WAN-1",
        public_ip="198.51.100.10",
    )

    site = Site(
        name="SITE-001",
        wan_links=(site_wan,),
    )

    datacenter = Datacenter(
        name="DC-01",
        wan_links=(dc_wan,),
    )

    tunnel = TunnelRequest(
        site_name=site.name,
        site_wan=site.wan_links[0],
        dc_name=datacenter.name,
        dc_wan=datacenter.wan_links[0],
    )

    assert tunnel.site_name == "SITE-001"
    assert tunnel.site_wan.public_ip == "203.0.113.10"
    assert tunnel.dc_name == "DC-01"
    assert tunnel.dc_wan.public_ip == "198.51.100.10"
