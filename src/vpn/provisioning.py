from dataclasses import dataclass

from src.vpn.addressing import TunnelAddressing
from src.vpn.models import TunnelRequest
from src.vpn.service import VPNAddressingService


@dataclass(frozen=True)
class ProvisionedTunnel:
    """VPN tunnel request enriched with allocated tunnel addressing."""

    request: TunnelRequest
    addressing: TunnelAddressing


def allocate_tunnel_topology(
    requests: tuple[TunnelRequest, ...],
    addressing_service: VPNAddressingService,
) -> tuple[ProvisionedTunnel, ...]:
    """Allocate one tunnel prefix for each requested VPN tunnel."""

    provisioned = []

    for request in requests:
        description = (
            f"{request.site_name}:{request.site_wan.name}"
            f"->{request.dc_name}:{request.dc_wan.name}"
        )

        addressing = addressing_service.allocate_tunnel(description)

        provisioned.append(
            ProvisionedTunnel(
                request=request,
                addressing=addressing,
            )
        )

    return tuple(provisioned)
