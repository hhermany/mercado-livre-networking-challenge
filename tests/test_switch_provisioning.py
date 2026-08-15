import pytest

from src.switch.provisioning import (
    BRANCH_STANDARD_V1,
    BranchVariables,
    classify_interfaces,
    render_branch_candidate,
)


def test_branch_profile_defaults():
    assert (
        BRANCH_STANDARD_V1[
            "management_vlan"
        ]
        == 255
    )

    assert (
        BRANCH_STANDARD_V1[
            "access_vlan"
        ]
        == 10
    )

    assert (
        BRANCH_STANDARD_V1[
            "voice_vlan"
        ]
        == 20
    )

    assert (
        BRANCH_STANDARD_V1[
            "snmp_community_ro"
        ]
        == "MercadoLibre007"
    )

    assert (
        BRANCH_STANDARD_V1[
            "admin_login_authentication"
        ]
        == "local"
    )

    assert (
        BRANCH_STANDARD_V1[
            "dot1x_mode"
        ]
        == "open"
    )


def test_classifies_user_uplink_and_preserved_interfaces():
    interfaces = [
        {
            "interface": "Gi1/0/1",
            "mode": "ACCESS · VLAN 10",
            "port_channel": "-",
        },
        {
            "interface": "Gi1/0/2",
            "mode": "ACCESS · VLAN 10",
            "port_channel": "-",
        },
        {
            "interface": "Gi1/0/47",
            "mode": "TRUNK",
            "port_channel": "Po1",
        },
        {
            "interface": "Gi1/0/48",
            "mode": "TRUNK",
            "port_channel": "-",
        },
        {
            "interface": "Gi0/0",
            "mode": "ROUTED",
            "ip_address": "172.28.255.10",
            "port_channel": "-",
        },
    ]

    classification = classify_interfaces(
        interfaces,
        uplink_interface="Gi1/0/48",
    )

    assert classification.uplink == (
        "Gi1/0/48"
    )

    assert classification.user_ports == [
        "Gi1/0/1",
        "Gi1/0/2",
    ]

    assert classification.preserved_ports == [
        "Gi0/0",
        "Gi1/0/47",
    ]


def test_rejects_unknown_uplink():
    with pytest.raises(
        ValueError,
        match="uplink",
    ):
        classify_interfaces(
            [
                {
                    "interface":
                        "Gi1/0/1",
                }
            ],
            uplink_interface=
                "Gi1/0/48",
        )


def test_renders_branch_candidate():
    variables = BranchVariables(
        hostname="BRANCH-01",
        management_ip="172.16.255.10",
        management_mask="255.255.255.0",
        default_gateway="172.16.255.1",
        uplink_interface="Gi1/0/48",
    )

    classification = classify_interfaces(
        [
            {
                "interface": "Gi1/0/1",
                "mode": "ROUTED",
                "ip_address": "172.28.255.11",
            },
            {
                "interface": "Gi1/0/2",
                "mode": "ACCESS",
            },
            {
                "interface": "Gi1/0/48",
                "mode": "TRUNK",
            },
        ],
        uplink_interface="Gi1/0/48",
    )

    config = render_branch_candidate(
        variables=variables,
        classification=classification,
    )

    assert (
        "hostname BRANCH-01"
        in config
    )

    assert (
        "interface Vlan255"
        in config
    )

    assert (
        "ip address 172.16.255.10 "
        "255.255.255.0"
        in config
    )

    assert (
        "ip default-gateway "
        "172.16.255.1"
        in config
    )

    assert (
        "interface Gi1/0/48"
        in config
    )

    assert (
        "switchport trunk allowed vlan "
        "10,20,255"
        in config
    )

    assert (
        "interface range Gi1/0/1 - 2"
        not in config
    )

    assert (
        "interface Gi1/0/2"
        in config
    )

    assert (
        "switchport access vlan 10"
        in config
    )

    assert (
        "switchport voice vlan 20"
        in config
    )

    assert (
        "authentication open"
        in config
    )

    assert (
        "aaa authentication login "
        "default local"
        in config
    )

    assert (
        "snmp-server community "
        "MercadoLibre007 RO"
        in config
    )


def test_interface_range_gi1_0_1_through_48():
    from src.switch.provisioning import (
        build_interface_groups,
    )

    interfaces = [
        f"Gi1/0/{port}"
        for port
        in range(
            1,
            49,
        )
    ]

    groups = (
        build_interface_groups(
            interfaces
        )
    )

    assert len(groups) == 1

    assert (
        groups[0]["mode"]
        == "range"
    )

    assert (
        groups[0]["command"]
        == "interface range Gi1/0/1 - 48"
    )


def test_interface_range_gi0_1_format():
    from src.switch.provisioning import (
        build_interface_groups,
    )

    groups = (
        build_interface_groups(
            [
                "Gi0/1",
                "Gi0/2",
                "Gi0/3",
            ]
        )
    )

    assert (
        groups[0]["command"]
        == "interface range Gi0/1 - 3"
    )


def test_interface_range_gi1_format():
    from src.switch.provisioning import (
        build_interface_groups,
    )

    groups = (
        build_interface_groups(
            [
                "Gi1",
                "Gi2",
                "Gi3",
            ]
        )
    )

    assert (
        groups[0]["command"]
        == "interface range Gi1 - 3"
    )


def test_interface_range_does_not_cross_slot():
    from src.switch.provisioning import (
        build_interface_groups,
    )

    groups = (
        build_interface_groups(
            [
                "Gi1/0/47",
                "Gi1/0/48",
                "Gi2/0/1",
                "Gi2/0/2",
            ]
        )
    )

    assert len(groups) == 2

    assert (
        groups[0]["interfaces"]
        == [
            "Gi1/0/47",
            "Gi1/0/48",
        ]
    )

    assert (
        groups[1]["interfaces"]
        == [
            "Gi2/0/1",
            "Gi2/0/2",
        ]
    )


def test_interface_range_does_not_invent_missing_ports():
    from src.switch.provisioning import (
        build_interface_groups,
    )

    groups = (
        build_interface_groups(
            [
                "Gi1/0/1",
                "Gi1/0/2",
                "Gi1/0/7",
                "Gi1/0/8",
            ]
        )
    )

    assert len(groups) == 2

    assert (
        groups[0]["interfaces"]
        == [
            "Gi1/0/1",
            "Gi1/0/2",
        ]
    )

    assert (
        groups[1]["interfaces"]
        == [
            "Gi1/0/7",
            "Gi1/0/8",
        ]
    )


def test_candidate_uses_only_discovered_user_ports():
    from src.switch.provisioning import (
        BranchVariables,
        classify_interfaces,
        render_branch_candidate,
    )

    variables = BranchVariables(
        hostname="BRANCH-RANGE",
        management_ip="172.16.255.10",
        management_mask="255.255.255.0",
        default_gateway="172.16.255.1",
        uplink_interface="Gi1/0/4",
    )

    classification = (
        classify_interfaces(
            [
                {
                    "interface": "Gi1/0/1",
                    "mode": "ROUTED",
                    "ip_address": "172.28.255.12",
                },
                {
                    "interface": "Gi1/0/2",
                    "mode": "ACCESS",
                },
                {
                    "interface": "Gi1/0/4",
                    "mode": "TRUNK",
                },
            ],
            uplink_interface=(
                "Gi1/0/4"
            ),
        )
    )

    config = (
        render_branch_candidate(
            variables=variables,
            classification=(
                classification
            ),
        )
    )

    assert (
        "interface range Gi1/0/1 - 2"
        not in config
    )

    assert (
        "interface Gi1/0/2"
        in config
    )

    assert (
        "Gi1/0/3"
        not in config
    )


def test_provision_port_is_first_physical_and_valid():
    from src.switch.provisioning import (
        discover_provision_port,
        validate_provision_port,
    )

    interfaces = [
        {
            "interface":
                "Vlan1",

            "mode":
                "ROUTED",

            "ip_address":
                "192.0.2.1",
        },
        {
            "interface":
                "Gi1/0/3",

            "mode":
                "ACCESS",
        },
        {
            "interface":
                "Gi1/0/1",

            "mode":
                "ROUTED",

            "ip_address":
                "172.28.255.101",
        },
        {
            "interface":
                "Gi1/0/2",

            "mode":
                "ACCESS",
        },
    ]

    provision_port = (
        discover_provision_port(
            interfaces
        )
    )

    assert (
        provision_port[
            "interface"
        ]
        == "Gi1/0/1"
    )

    validation = (
        validate_provision_port(
            provision_port
        )
    )

    assert (
        validation[
            "valid"
        ]
        is True
    )

    assert (
        validation[
            "ip_address"
        ]
        == "172.28.255.101"
    )


def test_rejects_provision_port_outside_management_network():
    from src.switch.provisioning import (
        validate_provision_port,
    )

    result = (
        validate_provision_port(
            {
                "interface":
                    "Gi0/0",

                "mode":
                    "ROUTED",

                "ip_address":
                    "192.168.1.10",
            }
        )
    )

    assert result[
        "valid"
    ] is False

    assert (
        "172.28.255.0/24"
        in " ".join(
            result[
                "errors"
            ]
        )
    )


def test_provision_port_never_enters_user_range():
    from src.switch.provisioning import (
        BranchVariables,
        classify_interfaces,
        render_branch_candidate,
    )

    interfaces = [
        {
            "interface":
                "Gi1/0/1",

            "mode":
                "ROUTED",

            "ip_address":
                "172.28.255.10",
        },
        {
            "interface":
                "Gi1/0/2",

            "mode":
                "ACCESS",
        },
        {
            "interface":
                "Gi1/0/3",

            "mode":
                "ACCESS",
        },
        {
            "interface":
                "Gi1/0/48",

            "mode":
                "TRUNK",
        },
    ]

    classification = (
        classify_interfaces(
            interfaces,
            uplink_interface=(
                "Gi1/0/48"
            ),
        )
    )

    assert (
        classification.provision_port
        == "Gi1/0/1"
    )

    assert (
        "Gi1/0/1"
        not in classification.user_ports
    )

    variables = BranchVariables(
        hostname="BRANCH-01",
        management_ip=(
            "10.255.255.10"
        ),
        management_mask=(
            "255.255.255.0"
        ),
        default_gateway=(
            "10.255.255.1"
        ),
        uplink_interface=(
            "Gi1/0/48"
        ),
    )

    config = (
        render_branch_candidate(
            variables=variables,
            classification=(
                classification
            ),
        )
    )

    assert (
        "interface Gi1/0/1"
        in config
    )

    assert (
        "description "
        "## PORTA PARA PROVISIONAMENTO ##"
        in config
    )

    assert (
        "description "
        "## PORTA PARA PROVISIONAMENTO ##"
        in config
    )

    assert (
        "interface range Gi1/0/1"
        not in config
    )


def test_provision_port_cannot_be_uplink():
    import pytest

    from src.switch.provisioning import (
        classify_interfaces,
    )

    with pytest.raises(
        ValueError,
        match="Provision Port",
    ):
        classify_interfaces(
            [
                {
                    "interface":
                        "Gi0/1",

                    "mode":
                        "ROUTED",

                    "ip_address":
                        "172.28.255.20",
                },
                {
                    "interface":
                        "Gi0/2",

                    "mode":
                        "ACCESS",
                },
            ],
            uplink_interface=
                "Gi0/1",
        )


def test_provision_accepts_name_based_inventory():
    from src.switch.provisioning import (
        classify_interfaces,
    )

    interfaces = [
        {
            "name": "Gi0/0",
            "mode_label": "Routed",
            "ip_address": "172.28.255.192",
        },
        {
            "name": "Gi0/1",
            "mode_label": "Access",
        },
        {
            "name": "Gi0/2",
            "mode_label": "Access",
        },
        {
            "name": "Gi1/0",
            "mode_label": "Access",
        },
        {
            "name": "Gi1/3",
            "mode_label": "Trunk",
        },
    ]

    classification = classify_interfaces(
        interfaces,
        uplink_interface="Gi1/3",
    )

    assert (
        classification.provision_port
        == "Gi0/0"
    )

    assert (
        classification.provision_ip
        == "172.28.255.192"
    )

    assert (
        "Gi0/0"
        not in classification.user_ports
    )

    assert classification.user_ports == [
        "Gi0/1",
        "Gi0/2",
        "Gi1/0",
    ]








def test_provision_port_only_receives_description():
    from src.switch.provisioning import (
        BranchVariables,
        classify_interfaces,
        render_branch_sections,
    )

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
        hostname="BRANCH-01",
        management_ip="10.255.255.10",
        management_mask="255.255.255.0",
        default_gateway="10.255.255.1",
        uplink_interface="Gi0/1",
    )

    section = render_branch_sections(
        variables=variables,
        classification=classification,
    )["provision_port"]

    assert (
        "interface Gi0/0"
        in section
    )

    assert (
        "## PORTA PARA PROVISIONAMENTO ##"
        in section
    )

    assert (
        "switchport"
        not in section
    )

    assert (
        "ip address"
        not in section
    )

    assert (
        "shutdown"
        not in section
    )
