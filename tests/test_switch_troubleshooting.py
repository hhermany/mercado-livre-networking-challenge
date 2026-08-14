import pytest

from src.switch.troubleshooting import (
    find_svi_by_name,
    parse_ipv4_targets,
    parse_svi_interfaces,
    validate_source_svi,
)

SHOW_IP_INTERFACE_BRIEF = """\
Interface              IP-Address      OK? Method Status                Protocol
GigabitEthernet0/0     172.28.255.210  YES manual up                    up
GigabitEthernet0/1     unassigned      YES unset  up                    up
Vlan10                 192.168.10.254  YES manual up                    up
Vlan20                 192.168.20.254  YES manual up                    up
Vlan50                 192.168.50.254  YES manual administratively down down
Vlan100                unassigned      YES unset  down                  down
"""


def test_parse_svi_interfaces():
    result = parse_svi_interfaces(
        SHOW_IP_INTERFACE_BRIEF
    )

    assert result == [
        {
            "name": "Vlan10",
            "ip_address": "192.168.10.254",
            "status": "up",
            "protocol": "up",
            "operational": True,
            "label": "Vlan10 - 192.168.10.254",
        },
        {
            "name": "Vlan20",
            "ip_address": "192.168.20.254",
            "status": "up",
            "protocol": "up",
            "operational": True,
            "label": "Vlan20 - 192.168.20.254",
        },
        {
            "name": "Vlan50",
            "ip_address": "192.168.50.254",
            "status": "administratively down",
            "protocol": "down",
            "operational": False,
            "label": "Vlan50 - 192.168.50.254",
        },
    ]


def test_parse_svi_ignores_physical_interfaces():
    result = parse_svi_interfaces(
        SHOW_IP_INTERFACE_BRIEF
    )

    assert all(
        item["name"].startswith("Vlan")
        for item in result
    )


def test_parse_svi_ignores_unassigned():
    result = parse_svi_interfaces(
        SHOW_IP_INTERFACE_BRIEF
    )

    assert all(
        item["name"] != "Vlan100"
        for item in result
    )


def test_parse_single_ipv4_target():
    assert parse_ipv4_targets(
        "8.8.8.8"
    ) == [
        "8.8.8.8"
    ]


def test_parse_multiple_ipv4_targets():
    assert parse_ipv4_targets(
        "8.8.8.8, 1.1.1.1"
    ) == [
        "8.8.8.8",
        "1.1.1.1",
    ]


def test_parse_ipv4_range():
    assert parse_ipv4_targets(
        "192.168.10.1-192.168.10.4"
    ) == [
        "192.168.10.1",
        "192.168.10.2",
        "192.168.10.3",
        "192.168.10.4",
    ]


def test_parse_combined_targets_and_range():
    assert parse_ipv4_targets(
        "8.8.8.8,"
        "192.168.10.1-192.168.10.3,"
        "1.1.1.1"
    ) == [
        "8.8.8.8",
        "192.168.10.1",
        "192.168.10.2",
        "192.168.10.3",
        "1.1.1.1",
    ]


def test_parse_targets_deduplicates_preserving_order():
    assert parse_ipv4_targets(
        "8.8.8.8,"
        "192.168.10.1-192.168.10.2,"
        "8.8.8.8,"
        "192.168.10.2"
    ) == [
        "8.8.8.8",
        "192.168.10.1",
        "192.168.10.2",
    ]


@pytest.mark.parametrize(
    "value",
    [
        "",
        "not-an-ip",
        "300.1.1.1",
        "192.168.10.10-192.168.10.1",
        "192.168.10.1-192.168.10.2-192.168.10.3",
    ],
)
def test_parse_targets_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        parse_ipv4_targets(value)


def test_parse_targets_enforces_limit():
    with pytest.raises(
        ValueError,
        match="limite de 3",
    ):
        parse_ipv4_targets(
            "192.168.10.1-192.168.10.4",
            max_targets=3,
        )


def test_find_svi_case_insensitive():
    svis = parse_svi_interfaces(
        SHOW_IP_INTERFACE_BRIEF
    )

    result = find_svi_by_name(
        svis,
        "vlan10",
    )

    assert result["ip_address"] == "192.168.10.254"


def test_validate_source_svi_accepts_up_up():
    svis = parse_svi_interfaces(
        SHOW_IP_INTERFACE_BRIEF
    )

    result = validate_source_svi(
        svis,
        "Vlan10",
    )

    assert result["operational"] is True


def test_validate_source_svi_rejects_non_operational():
    svis = parse_svi_interfaces(
        SHOW_IP_INTERFACE_BRIEF
    )

    with pytest.raises(
        ValueError,
        match="não está operacional",
    ):
        validate_source_svi(
            svis,
            "Vlan50",
        )


def test_validate_source_svi_rejects_unknown_svi():
    svis = parse_svi_interfaces(
        SHOW_IP_INTERFACE_BRIEF
    )

    with pytest.raises(
        ValueError,
        match="não encontrada",
    ):
        validate_source_svi(
            svis,
            "Vlan999",
        )


def test_parse_ping_result_success():
    from src.switch.troubleshooting import (
        parse_ping_result,
    )

    output = """\
Type escape sequence to abort.
Sending 5, 100-byte ICMP Echos to 192.168.20.254, timeout is 2 seconds:
!!!!!
Success rate is 100 percent (5/5), round-trip min/avg/max = 1/2/4 ms
"""

    result = parse_ping_result(output)

    assert result == {
        "success": True,
        "success_rate": 100,
        "received": 5,
        "sent": 5,
        "rtt_min_ms": 1,
        "rtt_avg_ms": 2,
        "rtt_max_ms": 4,
    }


def test_parse_ping_result_failure():
    from src.switch.troubleshooting import (
        parse_ping_result,
    )

    output = """\
Sending 5, 100-byte ICMP Echos to 203.0.113.10, timeout is 2 seconds:
.....
Success rate is 0 percent (0/5)
"""

    result = parse_ping_result(output)

    assert result["success"] is False
    assert result["success_rate"] == 0
    assert result["received"] == 0
    assert result["sent"] == 5
    assert result["rtt_avg_ms"] is None
