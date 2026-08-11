from collections.abc import Callable

from src.ipam.base import IPAMProvider
from src.vpn.addressing import TunnelAddressing, build_tunnel_addressing


class VPNAddressingService:
    """Coordinate IPAM allocation and VPN tunnel addressing."""

    def __init__(self, ipam_provider: IPAMProvider) -> None:
        self.ipam_provider = ipam_provider

    def allocate_tunnel(self, description: str) -> TunnelAddressing:
        """Allocate a /30 prefix and build endpoint addressing."""

        prefix = self.ipam_provider.allocate_prefix(
            prefix_length=30,
            description=description,
        )

        return build_tunnel_addressing(
            prefix_id=prefix["id"],
            prefix=prefix["prefix"],
        )

    def allocate_with_rollback(
        self,
        description: str,
        operation: Callable[[TunnelAddressing], None],
    ) -> TunnelAddressing:
        """Allocate addressing and release it if the next operation fails."""

        tunnel = self.allocate_tunnel(description)

        try:
            operation(tunnel)
        except Exception:
            self.release_tunnel(tunnel.prefix_id)
            raise

        return tunnel

    def release_tunnel(self, prefix_id: str) -> None:
        """Release the prefix associated with a VPN tunnel."""

        self.ipam_provider.release_prefix(prefix_id)
