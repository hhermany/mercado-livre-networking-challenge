from src.branch.paloalto_configuration import generate_paloalto_branch_config


def test_generate_paloalto_branch_2():
    config = generate_paloalto_branch_config(
        branch_id=2,
        branch_wan1_ip="100.64.0.3",
        branch_wan2_ip="100.100.0.3",
        psk="TEST-PSK",
    )

    assert "BRANCH-2-VPN1" in config
    assert "BRANCH-2-VPN2" in config

    assert "ethernet1/1" in config
    assert "ethernet1/3" in config

    assert "100.64.0.3" in config
    assert "100.100.0.3" in config
    assert 'key "TEST-PSK"' in config

    assert "tunnel.3" in config
    assert "tunnel.4" in config

    assert "169.255.2.1/30" in config
    assert "169.255.2.5/30" in config

    assert "169.255.2.2" in config
    assert "169.255.2.6" in config

    assert "FG-BRANCH-2-VPN1" in config
    assert "FG-BRANCH-2-VPN2" in config
    assert "IBGP-SDWAN" in config
