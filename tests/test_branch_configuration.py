from src.branch.configuration import generate_fortigate_branch_config


def test_generate_branch_2_config():
    config = generate_fortigate_branch_config(
        branch_id=2,
        psk="TEST-PSK",
        dc_wan1_ip="100.64.0.1",
        dc_wan2_ip="100.100.0.1",
    )

    assert "FW-BRANCH-2" in config
    assert "10.0.1.254" in config
    assert "172.31.255.2" in config
    assert "169.255.2.1" in config
    assert "169.255.2.2" in config
    assert "169.255.2.5" in config
    assert "169.255.2.6" in config
    assert "SLA_DC" in config
    assert "RM-OUT-VPN1" in config
