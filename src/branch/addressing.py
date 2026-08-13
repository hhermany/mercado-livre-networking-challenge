from dataclasses import dataclass


@dataclass(frozen=True)
class BranchPlan:
    branch_id: int
    name: str
    hostname: str
    lan_prefix: str
    loopback_prefix: str
    vpn1_prefix: str
    vpn2_prefix: str


def build_branch_plan(branch_id: int) -> BranchPlan:
    if not 1 <= branch_id <= 254:
        raise ValueError("Branch ID must be between 1 and 254.")

    lan_octet = branch_id - 1

    return BranchPlan(
        branch_id=branch_id,
        name=f"BRANCH-{branch_id}",
        hostname=f"FW-BRANCH-{branch_id}",
        lan_prefix=f"10.0.{lan_octet}.0/24",
        loopback_prefix=f"172.31.255.{branch_id}/32",
        vpn1_prefix=f"169.255.{branch_id}.0/30",
        vpn2_prefix=f"169.255.{branch_id}.4/30",
    )
