from dataclasses import dataclass
from ipaddress import IPv4Network

VPN_POOL = IPv4Network("169.255.0.0/16")
VPN_PREFIX_LENGTH = 30
VPN_TUNNELS_PER_BRANCH = 2


@dataclass(frozen=True)
class BranchPlan:
    branch_id: int
    name: str
    hostname: str
    lan_prefix: str
    loopback_prefix: str
    vpn1_prefix: str
    vpn2_prefix: str


def _vpn_prefix(
    branch_id: int,
    tunnel_index: int,
) -> str:
    if not 1 <= branch_id <= 254:
        raise ValueError("Branch ID must be between 1 and 254.")

    if tunnel_index not in (0, 1):
        raise ValueError("Tunnel index must be 0 or 1.")

    # BRANCH-1 e o golden template e nao participa
    # da alocacao automatica.
    #
    # O onboarding automatico inicia em BRANCH-2:
    #
    # BRANCH-2:
    #   VPN1 169.255.0.0/30
    #   VPN2 169.255.0.4/30
    #
    # BRANCH-3:
    #   VPN1 169.255.0.8/30
    #   VPN2 169.255.0.12/30
    #
    # BRANCH-33:
    #   VPN1 169.255.0.248/30
    #   VPN2 169.255.0.252/30
    #
    # BRANCH-34:
    #   VPN1 169.255.1.0/30
    #
    # Para permitir reconstruir o golden nos testes,
    # BRANCH-1 referencia o inicio do mesmo pool,
    # mas nunca e reservado pelo auto-onboarding.
    allocation_branch_id = max(
        branch_id,
        2,
    )

    subnet_index = (allocation_branch_id - 2) * VPN_TUNNELS_PER_BRANCH + tunnel_index

    subnet_size = 1 << (32 - VPN_PREFIX_LENGTH)

    network_address = int(VPN_POOL.network_address) + subnet_index * subnet_size

    network = IPv4Network(
        (
            network_address,
            VPN_PREFIX_LENGTH,
        )
    )

    if not network.subnet_of(VPN_POOL):
        raise ValueError("VPN address pool exhausted.")

    return str(network)


def build_branch_plan(
    branch_id: int,
) -> BranchPlan:
    if not 1 <= branch_id <= 254:
        raise ValueError("Branch ID must be between 1 and 254.")

    return BranchPlan(
        branch_id=branch_id,
        name=f"BRANCH-{branch_id}",
        hostname=f"FW-BRANCH-{branch_id}",
        lan_prefix=(f"10.0.{branch_id - 1}.0/24"),
        loopback_prefix=(f"172.31.255.{branch_id}/32"),
        vpn1_prefix=_vpn_prefix(
            branch_id,
            0,
        ),
        vpn2_prefix=_vpn_prefix(
            branch_id,
            1,
        ),
    )
