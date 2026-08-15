from src.switch.provisioning import (
    BranchVariables,
    classify_interfaces,
    render_branch_candidate,
    render_branch_sections,
)


def build_candidate():
    classification = classify_interfaces(
        [
            {
                "interface": "Gi0/0",
                "mode": "ROUTED",
                "ip_address": "172.28.255.10",
            },
            {
                "interface": "Gi0/1",
                "mode": "ACCESS",
            },
            {
                "interface": "Gi0/2",
                "mode": "ACCESS",
            },
            {
                "interface": "Gi0/3",
                "mode": "TRUNK",
            },
        ],
        uplink_interface="Gi0/3",
    )

    variables = BranchVariables(
        hostname="SW-BASELINE",
        management_ip="10.255.255.10",
        management_mask="255.255.255.0",
        default_gateway="10.255.255.1",
        uplink_interface="Gi0/3",
    )

    return render_branch_candidate(
        variables=variables,
        classification=classification,
    )


def test_aaa_minimum_contract_is_present():
    config = build_candidate()

    required = [
        "aaa new-model",
        "aaa group server radius RAD",
        " server name RAD1",
        " server name RAD2",
        (
            "aaa authentication login "
            "default local"
        ),
        (
            "aaa authentication dot1x "
            "default group RAD"
        ),
        (
            "aaa authorization exec "
            "default local"
        ),
        (
            "aaa authorization network "
            "default group RAD"
        ),
        (
            "aaa authorization auth-proxy "
            "default group RAD"
        ),
        (
            "aaa accounting update "
            "newinfo periodic 2880"
        ),
        (
            "aaa accounting dot1x "
            "default start-stop group RAD"
        ),
        (
            "aaa accounting system "
            "default start-stop group RAD"
        ),
        (
            "aaa server radius "
            "dynamic-author"
        ),
        (
            " client 192.168.0.178 "
            "server-key 7 13061E010803"
        ),
        (
            " client 192.168.0.177 "
            "server-key 7 0822455D0A16"
        ),
        "aaa session-id common",
    ]

    for command in required:
        assert command in config


def test_required_aaa_sequence_is_preserved():
    config = build_candidate()

    commands = [
        "aaa new-model",
        "aaa group server radius RAD",
        (
            "aaa authentication login "
            "default local"
        ),
        (
            "aaa authentication dot1x "
            "default group RAD"
        ),
        (
            "aaa authorization exec "
            "default local"
        ),
        (
            "aaa authorization network "
            "default group RAD"
        ),
        (
            "aaa authorization auth-proxy "
            "default group RAD"
        ),
        (
            "aaa accounting update "
            "newinfo periodic 2880"
        ),
        (
            "aaa accounting dot1x "
            "default start-stop group RAD"
        ),
        (
            "aaa accounting system "
            "default start-stop group RAD"
        ),
        (
            "aaa server radius "
            "dynamic-author"
        ),
        "aaa session-id common",
    ]

    positions = [
        config.index(
            command
        )
        for command
        in commands
    ]

    assert positions == sorted(
        positions
    )


def test_dot1x_global_precedes_user_interfaces():
    config = build_candidate()

    assert (
        config.index(
            "aaa new-model"
        )
        <
        config.index(
            "aaa authentication dot1x "
            "default group RAD"
        )
        <
        config.index(
            "dot1x system-auth-control"
        )
        <
        config.index(
            "interface range Gi0/1 - 2"
        )
        <
        config.index(
            " authentication open"
        )
    )


def test_domain_is_mercadolivre_local():
    config = build_candidate()

    assert (
        "ip domain name "
        "MercadoLivre.local"
        in config
    )

    assert (
        "unimed"
        not in config.lower()
    )


def test_radius_names_and_keys_are_fixed():
    config = build_candidate()

    assert (
        "radius server RAD1"
        in config
    )

    assert (
        "radius server RAD2"
        in config
    )

    assert (
        "key 7 094F471A1A0A"
        in config
    )

    assert (
        "key 7 070C285F4D06"
        in config
    )


def test_radius_source_uses_vlan255():
    config = build_candidate()

    assert (
        "ip radius source-interface "
        "Vlan255"
        in config
    )






def test_provision_port_is_still_protected():
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
        hostname="SW-PROVISION",
        management_ip="10.255.255.10",
        management_mask="255.255.255.0",
        default_gateway="10.255.255.1",
        uplink_interface="Gi0/1",
    )

    section = render_branch_sections(
        variables=variables,
        classification=classification,
    )[
        "provision_port"
    ]

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
