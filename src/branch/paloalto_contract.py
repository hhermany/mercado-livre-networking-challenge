from dataclasses import dataclass


@dataclass(frozen=True)
class PaloAltoBranchPlan:
    branch_id: int
    tunnel1_id: int
    tunnel2_id: int
    tunnel1_name: str
    tunnel2_name: str
    ipsec1_name: str
    ipsec2_name: str
    bgp_peer1_name: str
    bgp_peer2_name: str


def build_paloalto_branch_plan(
    branch_id: int,
) -> PaloAltoBranchPlan:
    if branch_id < 1:
        raise ValueError("branch_id deve ser >= 1")

    tunnel1_id = ((branch_id - 1) * 2) + 1

    tunnel2_id = tunnel1_id + 1

    return PaloAltoBranchPlan(
        branch_id=branch_id,
        tunnel1_id=tunnel1_id,
        tunnel2_id=tunnel2_id,
        tunnel1_name=f"tunnel.{tunnel1_id}",
        tunnel2_name=f"tunnel.{tunnel2_id}",
        ipsec1_name=f"BRANCH-{branch_id}-VPN1",
        ipsec2_name=f"BRANCH-{branch_id}-VPN2",
        bgp_peer1_name=(f"FG-BRANCH-{branch_id}-VPN1"),
        bgp_peer2_name=(f"FG-BRANCH-{branch_id}-VPN2"),
    )
