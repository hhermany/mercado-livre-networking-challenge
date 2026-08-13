from dataclasses import dataclass

from src.branch.addressing import build_branch_plan
from src.branch.configuration import generate_fortigate_branch_config
from src.branch.paloalto_configuration import generate_paloalto_branch_config


@dataclass(frozen=True)
class BranchBundle:
    branch_id: int
    name: str
    hostname: str
    fortigate: str
    paloalto: str


def generate_branch_bundle(
    branch_id: int,
    branch_wan1_ip: str,
    branch_wan2_ip: str,
    dc_wan1_ip: str,
    dc_wan2_ip: str,
    psk: str,
) -> BranchBundle:
    plan = build_branch_plan(branch_id)

    fortigate = generate_fortigate_branch_config(
        branch_id=branch_id,
        psk=psk,
        dc_wan1_ip=dc_wan1_ip,
        dc_wan2_ip=dc_wan2_ip,
    )

    paloalto = generate_paloalto_branch_config(
        branch_id=branch_id,
        branch_wan1_ip=branch_wan1_ip,
        branch_wan2_ip=branch_wan2_ip,
        psk=psk,
    )

    return BranchBundle(
        branch_id=branch_id,
        name=plan.name,
        hostname=plan.hostname,
        fortigate=fortigate,
        paloalto=paloalto,
    )
