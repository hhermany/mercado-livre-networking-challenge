from src.branch.bundle import generate_branch_bundle
from src.branch.models import (
    BranchWANInput,
    IPsecPhase1Input,
    IPsecPhase2Input,
)


def test_generate_branch_2_bundle():
    bundle = generate_branch_bundle(
        branch_id=2,
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
        dc_wan1_ip="100.64.0.1",
        dc_wan2_ip="100.100.0.1",
    )

    assert bundle.name == "BRANCH-2"
    assert bundle.hostname == "FW-BRANCH-2"

    assert "FW-BRANCH-2" in bundle.fortigate

    assert "set ip 100.64.0.3 255.255.255.0" in bundle.fortigate

    assert "set ip 100.100.0.3 255.255.255.0" in bundle.fortigate

    assert "172.31.255.2" in bundle.fortigate
    assert "169.255.0.2" in bundle.fortigate
    assert "169.255.0.6" in bundle.fortigate

    assert '"VPN1-PA-DC"' in bundle.fortigate

    assert '"VPN2-PA-DC"' in bundle.fortigate

    assert "BRANCH-2-VPN1" in bundle.paloalto
    assert "BRANCH-2-VPN2" in bundle.paloalto

    assert "169.255.0.1/30" in bundle.paloalto

    assert "169.255.0.5/30" in bundle.paloalto

    assert "100.64.0.3" in bundle.paloalto

    assert "100.100.0.3" in bundle.paloalto

    assert 'key "TEST-PSK"' in bundle.paloalto
