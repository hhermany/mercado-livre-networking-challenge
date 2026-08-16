import src.branch.onboarding as onboarding
from src.branch.addressing import (
    build_branch_plan,
)
from src.branch.models import (
    BranchProvisionInput,
    BranchWANInput,
    IPsecPhase1Input,
    IPsecPhase2Input,
)


class FakeProvisioner:
    def provision(self):
        return build_branch_plan(3)


def test_onboard_next_branch(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        onboarding,
        "BranchProvisioner",
        FakeProvisioner,
    )

    provision = BranchProvisionInput(
        hostname="FW-BRANCH-3",
        wan=BranchWANInput(
            wan1_ip="100.64.0.4/24",
            wan1_gateway="100.64.0.1",
            wan2_ip="100.100.0.4/24",
            wan2_gateway="100.100.0.1",
        ),
        phase1=IPsecPhase1Input(
            ike_version=2,
            proposal="des-sha256",
            dh_group=14,
            psk="TEST-PSK",
        ),
        phase2=IPsecPhase2Input(
            proposal="des-sha256",
            dh_group=14,
        ),
    )

    result = onboarding.onboard_next_branch(
        provision=provision,
        dc_wan1_ip="100.64.0.1",
        dc_wan2_ip="100.100.0.1",
        output_root=str(tmp_path),
    )

    assert result.bundle.name == "BRANCH-3"

    assert result.bundle.hostname == "FW-BRANCH-3"

    assert "100.64.0.4" in result.bundle.fortigate

    assert "100.100.0.4" in result.bundle.fortigate

    assert "172.31.255.3" in result.bundle.fortigate

    assert "169.255.0.10" in result.bundle.fortigate

    assert "169.255.0.14" in result.bundle.fortigate

    assert "169.255.0.9/30" in result.bundle.paloalto

    assert "169.255.0.13/30" in result.bundle.paloalto

    assert tmp_path.joinpath(
        "BRANCH-3",
        "fortigate.conf",
    ).exists()

    assert tmp_path.joinpath(
        "BRANCH-3",
        "paloalto.set",
    ).exists()
