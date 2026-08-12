from dataclasses import dataclass

from src.templates.renderer import TemplateRenderer
from src.vpn.provisioning import ProvisionedTunnel


@dataclass(frozen=True)
class GeneratedTunnelConfig:
    """Rendered configuration for both VPN endpoints."""

    fortigate: str
    paloalto: str


class VPNConfigurationGenerator:
    """Render FortiGate and Palo Alto configuration for a VPN tunnel."""

    def __init__(self, renderer: TemplateRenderer) -> None:
        self.renderer = renderer

    def generate(
        self,
        tunnel: ProvisionedTunnel,
        psk: str,
        fortigate_interface: str,
        paloalto_interface: str,
        paloalto_tunnel_interface: str,
    ) -> GeneratedTunnelConfig:
        """Generate vendor-specific configuration for one tunnel."""

        tunnel_name = (
            f"{tunnel.request.site_name}-"
            f"{tunnel.request.site_wan.name}-"
            f"{tunnel.request.dc_name}-"
            f"{tunnel.request.dc_wan.name}"
        )

        fortigate_config = self.renderer.render(
            "fortigate/ipsec_tunnel.j2",
            {
                "tunnel_name": tunnel_name,
                "wan_interface": fortigate_interface,
                "remote_public_ip": tunnel.request.dc_wan.public_ip,
                "psk": psk,
            },
        )

        paloalto_config = self.renderer.render(
            "paloalto/ipsec_tunnel.j2",
            {
                "tunnel_name": tunnel_name,
                "wan_interface": paloalto_interface,
                "remote_public_ip": tunnel.request.site_wan.public_ip,
                "psk": psk,
                "tunnel_interface": paloalto_tunnel_interface,
            },
        )

        return GeneratedTunnelConfig(
            fortigate=fortigate_config,
            paloalto=paloalto_config,
        )
