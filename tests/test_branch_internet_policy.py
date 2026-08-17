from src.branch.configuration import (
    generate_fortigate_branch_config,
)
from src.branch.models import (
    BranchWANInput,
    IPsecPhase1Input,
    IPsecPhase2Input,
)


def build_config():
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


def internet_policy(config):
    start = config.index(
        'set name "BRANCH-LAN-to-INTERNET"'
    )

    end = config.index(
        "\n    next",
        start,
    )

    return config[start:end]


def test_branch_has_lan_to_internet_policy():
    policy = internet_policy(
        build_config()
    )

    assert 'set srcintf "port4"' in policy
    assert 'set dstintf "WAN-INTERNET"' in policy
    assert "set action accept" in policy

    assert 'set srcaddr "BRANCH-LAN"' in policy
    assert 'set dstaddr "all"' in policy

    assert 'set schedule "always"' in policy


def test_internet_policy_allows_expected_services():
    policy = internet_policy(
        build_config()
    )

    assert (
        'set service "PING" "HTTP" "HTTPS"'
        in policy
    )


def test_internet_policy_enables_nat():
    policy = internet_policy(
        build_config()
    )

    assert "set nat enable" in policy


def test_internet_policy_logs_traffic():
    policy = internet_policy(
        build_config()
    )

    assert "set logtraffic all" in policy
