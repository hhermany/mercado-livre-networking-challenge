from src.templates.renderer import TemplateRenderer
from src.vpn.addressing import TunnelAddressing
from src.vpn.configuration import VPNConfigurationGenerator
from src.vpn.models import TunnelRequest, WANLink
from src.vpn.provisioning import ProvisionedTunnel


def test_generate_vendor_configs() -> None:
    tunnel = ProvisionedTunnel(
        request=TunnelRequest(
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
        addressing=TunnelAddressing(
            prefix_id="prefix-test-id",
            prefix="169.255.0.0/30",
            site_ip="169.255.0.1",
            dc_ip="169.255.0.2",
        ),
    )

    generator = VPNConfigurationGenerator(TemplateRenderer())

    config = generator.generate(
        tunnel=tunnel,
        psk="test-secret",
        fortigate_interface="port1",
        paloalto_interface="ethernet1/1",
        paloalto_tunnel_interface="tunnel.10",
    )

    assert 'edit "SITE-001-WAN-1-DC-01-WAN-1"' in config.fortigate
    assert "set remote-gw 198.51.100.10" in config.fortigate

    assert (
        "set network ike gateway SITE-001-WAN-1-DC-01-WAN-1"
        in config.paloalto
    )
    assert "peer-address ip 203.0.113.10" in config.paloalto
    assert "tunnel-interface tunnel.10" in config.paloalto
