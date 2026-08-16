from dataclasses import dataclass
from pathlib import Path

from src.branch.bundle import (
    BranchBundle,
    generate_branch_bundle,
)
from src.branch.models import (
    BranchProvisionInput,
)
from src.branch.provisioning import (
    BranchProvisioner,
)


@dataclass(frozen=True)
class OnboardingResult:
    bundle: BranchBundle
    output_dir: str


def onboard_next_branch(
    provision: BranchProvisionInput,
    dc_wan1_ip: str,
    dc_wan2_ip: str,
    output_root: str = "generated",
) -> OnboardingResult:
    provisioner = BranchProvisioner()

    plan = provisioner.provision()

    bundle = generate_branch_bundle(
        branch_id=plan.branch_id,
        wan=provision.wan,
        phase1=provision.phase1,
        phase2=provision.phase2,
        dc_wan1_ip=dc_wan1_ip,
        dc_wan2_ip=dc_wan2_ip,
        hostname=provision.hostname,
    )

    output_dir = Path(output_root) / plan.name

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    (output_dir / "fortigate.conf").write_text(bundle.fortigate)

    (output_dir / "paloalto.set").write_text(bundle.paloalto)

    return OnboardingResult(
        bundle=bundle,
        output_dir=str(output_dir),
    )
