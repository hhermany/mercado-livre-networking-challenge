from src.branch.paloalto_compliance import (
    PaloAltoGoldenCompliance,
)
from src.branch.paloalto_configuration import (
    generate_paloalto_branch_config,
)


def candidate():
    return generate_paloalto_branch_config(
        branch_id=2,
        branch_wan1_ip="100.64.0.3",
        branch_wan2_ip="100.100.0.3",
        psk="TEST-PSK",
    )


def evaluate(config):
    return PaloAltoGoldenCompliance().evaluate(
        candidate=config,
        branch_id=2,
        wan1_pa_ip="100.64.0.1/24",
        wan1_fg_ip="100.64.0.3",
        wan2_pa_ip="100.100.0.1/24",
        wan2_fg_ip="100.100.0.3",
        vpn1_pa_ip="169.255.0.1",
        vpn1_fg_ip="169.255.0.2",
        vpn2_pa_ip="169.255.0.5",
        vpn2_fg_ip="169.255.0.6",
    )


def test_candidate_matches_contract():
    report = evaluate(candidate())

    assert report.success, report.render()


def test_branch_2_is_added_to_filiais_zone():
    config = candidate()

    assert "set zone FILIAIS network layer3 tunnel.3" in config

    assert "set zone FILIAIS network layer3 tunnel.4" in config


def test_tunnel_management_profile_is_reused():
    config = candidate()

    assert config.count("interface-management-profile TUNNEL-MGMT") == 2


def test_candidate_does_not_create_security_policies():
    config = candidate()

    assert "set rulebase security rules" not in config


def test_detects_zone_regression():
    config = candidate().replace(
        "set zone FILIAIS",
        "set zone BROKEN",
    )

    report = evaluate(config)

    assert not report.success


def test_detects_tunnel_interface_regression():
    config = candidate().replace(
        "tunnel.3",
        "tunnel.999",
    )

    report = evaluate(config)

    assert not report.success
