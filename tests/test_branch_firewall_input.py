from src.branch.models import (
    BranchProvisionInput,
    BranchWANInput,
    IPsecPhase1Input,
    IPsecPhase2Input,
)


def test_branch_provision_input_contract():
    data = BranchProvisionInput(
        hostname="FW-BRANCH-2",
        wan=BranchWANInput(
            wan1_ip="100.64.0.3/24",
            wan1_gateway="100.64.0.1",
            wan2_ip="100.100.0.3/24",
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

    assert data.hostname == "FW-BRANCH-2"

    assert data.wan.wan1_ip == "100.64.0.3/24"
    assert data.wan.wan1_gateway == "100.64.0.1"

    assert data.wan.wan2_ip == "100.100.0.3/24"
    assert data.wan.wan2_gateway == "100.100.0.1"

    assert data.phase1.ike_version == 2
    assert data.phase1.proposal == "des-sha256"
    assert data.phase1.dh_group == 14
    assert data.phase1.psk == "TEST-PSK"

    assert data.phase2.proposal == "des-sha256"
    assert data.phase2.dh_group == 14
