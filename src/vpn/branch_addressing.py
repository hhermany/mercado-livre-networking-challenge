from dataclasses import dataclass
from ipaddress import IPv4Network


@dataclass(frozen=True)
class BranchAddressing:
    branch_id: int
    name: str
    hostname: str
    lan_prefix: str
    loopback_prefix: str


def build_branch_addressing(
    branch_id: int,
    lan_prefix: str,
    loopback_prefix: str,
) -> BranchAddressing:

    if branch_id < 1:
        raise ValueError("Branch ID must be greater than zero.")

    lan = IPv4Network(lan_prefix)
    loopback = IPv4Network(loopback_prefix)

    if lan.prefixlen != 24:
        raise ValueError("Branch LAN addressing requires a /24 prefix.")

    if loopback.prefixlen != 32:
        raise ValueError("Branch management loopback requires a /32 prefix.")

    return BranchAddressing(
        branch_id=branch_id,
        name=f"BRANCH-{branch_id}",
        hostname=f"FW-BRANCH-{branch_id}",
        lan_prefix=str(lan),
        loopback_prefix=str(loopback),
    )
