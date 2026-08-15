from src.switch.provisioning.deploy import (
    candidate_command_count,
    split_candidate_blocks,
)


def test_candidate_is_split_on_bang():
    config = """
hostname SW-01
!
aaa new-model
!
aaa group server radius RAD
 server name RAD1
 server name RAD2
!
interface Vlan255
 description ## MANAGEMENT ##
 ip address 10.10.10.1 255.255.255.0
 no shutdown
!
end
"""

    blocks = split_candidate_blocks(
        config
    )

    assert len(blocks) == 4

    assert blocks[0].commands == (
        "hostname SW-01",
    )

    assert blocks[1].commands == (
        "aaa new-model",
    )

    assert blocks[2].commands == (
        "aaa group server radius RAD",
        "server name RAD1",
        "server name RAD2",
    )

    assert blocks[3].commands == (
        "interface Vlan255",
        "description ## MANAGEMENT ##",
        (
            "ip address 10.10.10.1 "
            "255.255.255.0"
        ),
        "no shutdown",
    )


def test_archive_context_is_preserved():
    config = """
archive
 log config
  logging enable
!
"""

    blocks = split_candidate_blocks(
        config
    )

    assert blocks[0].commands == (
        "archive",
        "log config",
        "logging enable",
    )


def test_radius_server_context_is_preserved():
    config = """
radius server RAD1
 address ipv4 192.168.0.178 auth-port 1645 acct-port 1646
 timeout 10
 retransmit 3
 automate-tester username dummy ignore-acct-port probe-on
 key 7 094F471A1A0A
!
"""

    blocks = split_candidate_blocks(
        config
    )

    assert len(blocks) == 1

    assert (
        blocks[0].first_command
        == "radius server RAD1"
    )

    assert (
        "key 7 094F471A1A0A"
        in blocks[0].commands
    )


def test_interface_range_context_is_preserved():
    config = """
interface range Gi0/1 - 3
 description ## PORTA-DE-USUARIO ##
 switchport access vlan 10
 switchport mode access
 authentication open
 mab
 dot1x pae authenticator
!
"""

    blocks = split_candidate_blocks(
        config
    )

    assert len(blocks) == 1

    assert (
        blocks[0].commands[0]
        == "interface range Gi0/1 - 3"
    )

    assert (
        blocks[0].commands[-1]
        == "dot1x pae authenticator"
    )


def test_wrappers_are_removed():
    config = """
configure terminal
!
hostname SW-01
!
end
"""

    blocks = split_candidate_blocks(
        config
    )

    commands = [
        command
        for block in blocks
        for command in block.commands
    ]

    assert commands == [
        "hostname SW-01"
    ]


def test_empty_candidate():
    assert (
        split_candidate_blocks(
            "!\n!\n"
        )
        == []
    )


def test_candidate_command_count():
    config = """
hostname SW-01
!
aaa new-model
!
vlan 10
 name DATA
!
"""

    assert (
        candidate_command_count(
            config
        )
        == 4
    )
