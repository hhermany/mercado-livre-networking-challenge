from copy import deepcopy

from src.switch.provisioning import (
    BRANCH_STANDARD_V1,
    BranchVariables,
    classify_interfaces,
    render_branch_candidate,
)


def test_snmp_baseline_is_minimal():
    profile = deepcopy(BRANCH_STANDARD_V1)

    classification = classify_interfaces(
        [
            {
                "interface": "Gi0/0",
                "mode": "ROUTED",
                "ip_address": "172.28.255.10",
            },
            {
                "interface": "Gi0/1",
                "mode": "TRUNK",
            },
        ],
        uplink_interface="Gi0/1",
    )

    variables = BranchVariables(
        hostname="SW-SNMP",
        management_ip="10.1.1.1",
        management_mask="255.255.255.0",
        default_gateway="10.1.1.254",
        uplink_interface="Gi0/1",
    )

    config = render_branch_candidate(
        variables=variables,
        classification=classification,
        profile=profile,
    )

    assert "snmp-server community MercadoLibre007 RO" in config

    assert "snmp-server host 192.168.0.167 version 2c MercadoLibre007" in config

    assert "snmp-server enable traps" not in config
