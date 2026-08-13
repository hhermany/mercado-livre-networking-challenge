from src.branch.models import BranchActivation, BranchWANInput


def test_branch_activation():
    activation = BranchActivation(
        branch_id=2,
        wan=BranchWANInput(
            wan1_ip="100.64.0.3/24",
            wan1_gateway="100.64.0.1",
            wan2_ip="100.100.0.3/24",
            wan2_gateway="100.100.0.1",
        ),
        psk="challenge-vpn-psk",
    )

    assert activation.branch_id == 2
    assert activation.wan.wan1_ip == "100.64.0.3/24"
