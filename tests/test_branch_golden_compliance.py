from src.branch.configuration import (
    generate_fortigate_branch_config,
)
from src.branch.golden_compliance import (
    FortiGateGoldenCompliance,
)
from src.branch.models import (
    BranchWANInput,
    IPsecPhase1Input,
    IPsecPhase2Input,
)


def build_candidate():
    return generate_fortigate_branch_config(
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


def evaluate(candidate):
    engine = FortiGateGoldenCompliance(golden_dir="golden")

    return engine.evaluate(
        candidate=candidate,
        branch_id=2,
        hostname="FW-BRANCH-2",
        lan_network="10.0.1.0",
        lan_gateway="10.0.1.254",
        loopback_ip="172.31.255.2",
        wan1_ip="100.64.0.3",
        wan2_ip="100.100.0.3",
        vpn1_pa_ip="169.255.0.1",
        vpn1_fg_ip="169.255.0.2",
        vpn2_pa_ip="169.255.0.5",
        vpn2_fg_ip="169.255.0.6",
    )


def test_real_candidate_matches_golden():
    report = evaluate(build_candidate())

    assert report.success, report.render()


def test_detects_missing_vpn_tunnel_type():
    candidate = build_candidate()

    engine = FortiGateGoldenCompliance(golden_dir="golden")

    section = engine._config_section_with_edit(
        candidate,
        "system interface",
        "VPN1-PA-DC",
    )

    vpn1 = engine._edit_block(
        section,
        "VPN1-PA-DC",
    )

    assert "set type tunnel" in vpn1

    broken_vpn1 = vpn1.replace(
        "set type tunnel",
        "set type BROKEN",
        1,
    )

    assert "set type tunnel" not in broken_vpn1

    candidate = candidate.replace(
        vpn1,
        broken_vpn1,
        1,
    )

    # Prova que o proprio parser do engine
    # enxerga o Candidate quebrado.
    broken_section = engine._config_section_with_edit(
        candidate,
        "system interface",
        "VPN1-PA-DC",
    )

    extracted = engine._edit_block(
        broken_section,
        "VPN1-PA-DC",
    )

    assert "set type BROKEN" in extracted
    assert "set type tunnel" not in extracted

    report = evaluate(candidate)

    assert not report.success

    vpn_check = next(check for check in report.checks if check.name == "VPN interfaces")

    assert not vpn_check.success

    assert "candidate VPN1: set type tunnel" in vpn_check.detail


def test_detects_missing_management_policy():
    candidate = build_candidate()

    candidate = candidate.replace(
        'set name "DC-to-FG-MGMT"',
        'set name "BROKEN"',
        1,
    )

    report = evaluate(candidate)

    assert not report.success

    assert any(
        check.name == "Firewall policies" and not check.success
        for check in report.checks
    )


def test_detects_static_route_regression():
    candidate = (
        build_candidate()
        + """
config router static
    edit 1
        set gateway 192.0.2.1
        set device "port2"
    next
end
"""
    )

    report = evaluate(candidate)

    assert not report.success

    assert any(
        check.name == "Static routing" and not check.success for check in report.checks
    )


def test_rendered_report_has_summary():
    report = evaluate(build_candidate())

    text = report.render()

    assert "FORTIGATE GOLDEN COMPLIANCE" in text

    assert "COMPLIANCE: VERDE" in text

    assert "Unexpected differences: 0" in text
