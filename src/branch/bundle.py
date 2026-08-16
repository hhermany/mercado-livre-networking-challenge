from dataclasses import dataclass
from ipaddress import IPv4Interface

from src.branch.addressing import build_branch_plan
from src.branch.configuration import generate_fortigate_branch_config
from src.branch.models import (
    BranchWANInput,
    IPsecPhase1Input,
    IPsecPhase2Input,
)
from src.branch.paloalto_configuration import (
    generate_paloalto_branch_config,
)


@dataclass(frozen=True)
class BranchBundle:
    branch_id: int
    name: str
    hostname: str
    fortigate: str
    paloalto: str


def generate_branch_bundle(
    branch_id: int,
    wan: BranchWANInput,
    phase1: IPsecPhase1Input,
    phase2: IPsecPhase2Input,
    dc_wan1_ip: str,
    dc_wan2_ip: str,
    hostname: str | None = None,
) -> BranchBundle:
    plan = build_branch_plan(branch_id)

    fortigate = generate_fortigate_branch_config(
        branch_id=branch_id,
        wan=wan,
        phase1=phase1,
        phase2=phase2,
        dc_wan1_ip=dc_wan1_ip,
        dc_wan2_ip=dc_wan2_ip,
        hostname=hostname,
    )

    paloalto = generate_paloalto_branch_config(
        branch_id=branch_id,
        branch_wan1_ip=str(IPv4Interface(wan.wan1_ip).ip),
        branch_wan2_ip=str(IPv4Interface(wan.wan2_ip).ip),
        psk=phase1.psk,
    )

    return BranchBundle(
        branch_id=branch_id,
        name=plan.name,
        hostname=hostname or plan.hostname,
        fortigate=fortigate,
        paloalto=paloalto,
    )
