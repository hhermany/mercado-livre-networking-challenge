import src.branch.onboarding as onboarding
from src.branch.addressing import build_branch_plan


class FakeProvisioner:
    def provision(self):
        return build_branch_plan(3)


def test_onboard_next_branch(monkeypatch, tmp_path):
    monkeypatch.setattr(
        onboarding,
        "BranchProvisioner",
        FakeProvisioner,
    )

    result = onboarding.onboard_next_branch(
        branch_wan1_ip="100.64.0.4",
        branch_wan2_ip="100.100.0.4",
        dc_wan1_ip="100.64.0.1",
        dc_wan2_ip="100.100.0.1",
        psk="TEST-PSK",
        output_root=str(tmp_path),
    )

    assert result.bundle.name == "BRANCH-3"
    assert result.bundle.hostname == "FW-BRANCH-3"

    assert "172.31.255.3" in result.bundle.fortigate
    assert "169.255.3.2" in result.bundle.fortigate
    assert "169.255.3.6" in result.bundle.fortigate

    assert "169.255.3.1/30" in result.bundle.paloalto
    assert "169.255.3.5/30" in result.bundle.paloalto
