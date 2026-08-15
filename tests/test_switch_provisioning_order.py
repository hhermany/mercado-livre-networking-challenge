from src.switch.provisioning import (
    BranchVariables,
    classify_interfaces,
    render_branch_candidate,
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
        hostname="BRANCH-ORDER",
        management_ip="10.255.255.10",
        management_mask="255.255.255.0",
        default_gateway="10.255.255.1",
        uplink_interface="Gi0/3",
    )

    return render_branch_candidate(
        variables=variables,
        classification=classification,
    )


def test_domain_is_mercadolivre():
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


def test_required_aaa_block_precedes_dot1x_interfaces():
    config = build_candidate()

    aaa_new_model = config.index(
        "aaa new-model"
    )

    radius_group = config.index(
        "aaa group server radius RAD"
    )

    aaa_login = config.index(
        "aaa authentication login "
        "default local"
    )

    aaa_dot1x = config.index(
        "aaa authentication dot1x "
        "default group RAD"
    )

    aaa_authorization = config.index(
        "aaa authorization network "
        "default group RAD"
    )

    aaa_accounting = config.index(
        "aaa accounting dot1x "
        "default start-stop group RAD"
    )

    coa = config.index(
        "aaa server radius "
        "dynamic-author"
    )

    dot1x_global = config.index(
        "dot1x system-auth-control"
    )

    user_interface = config.index(
        "interface range Gi0/1 - 2"
    )

    interface_auth = config.index(
        " authentication open"
    )

    assert (
        aaa_new_model
        < radius_group
        < aaa_login
        < aaa_dot1x
        < aaa_authorization
        < aaa_accounting
        < coa
        < dot1x_global
        < user_interface
        < interface_auth
    )


def test_complete_aaa_contract_exists():
    config = build_candidate()

    required = (
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
        "aaa server radius dynamic-author",
        "aaa session-id common",
    )

    for command in required:
        assert command in config


def test_radius_source_matches_management_vlan():
    config = build_candidate()

    assert (
        "ip radius source-interface "
        "Vlan255"
        in config
    )


def test_radius_source_follows_user_interfaces_in_candidate():
    config = build_candidate()

    users = config.index(
        "interface range Gi0/1 - 2"
    )

    source = config.index(
        "ip radius source-interface "
        "Vlan255"
    )

    assert (
        users
        < source
    )


def test_admin_login_uses_local_default():
    config = build_candidate()

    assert (
        "aaa authentication login "
        "default local"
        in config
    )

    assert (
        "aaa authorization exec "
        "default local"
        in config
    )

    assert (
        "aaa authentication login "
        "default group RAD"
        not in config
    )

    assert (
        "LOCAL-ADMIN"
        not in config
    )




def test_radius_server_definitions_use_rad1_rad2():
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
        "radius server ISE"
        not in config
    )

    assert (
        "radius server ISE2"
        not in config
    )
