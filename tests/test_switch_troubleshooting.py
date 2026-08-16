import pytest

from src.switch.troubleshooting import (
    find_l3_interface_by_name,
    parse_ipv4_targets,
    parse_l3_interfaces,
    parse_ping_result,
    validate_source_interface,
)

SHOW_IP_INTERFACE_BRIEF = """\
Interface              IP-Address      OK? Method Status                Protocol
GigabitEthernet0/0     172.28.255.210  YES manual up                    up
GigabitEthernet0/1     unassigned      YES unset  up                    up
GigabitEthernet0/2     unassigned      YES unset  administratively down down
Vlan10                 192.168.10.254  YES manual up                    up
Vlan20                 192.168.20.254  YES manual up                    up
Vlan50                 192.168.50.254  YES manual administratively down down
Vlan100                unassigned      YES unset  down                  down
"""


def test_parse_l3_interfaces_includes_routed_physical_and_svi():
    result = parse_l3_interfaces(SHOW_IP_INTERFACE_BRIEF)

    names = [item["name"] for item in result]

    assert names == [
        "GigabitEthernet0/0",
        "Vlan10",
        "Vlan20",
        "Vlan50",
    ]


def test_parse_l3_interface_physical_routed():
    result = parse_l3_interfaces(SHOW_IP_INTERFACE_BRIEF)

    interface = result[0]

    assert interface == {
        "name": "GigabitEthernet0/0",
        "ip_address": "172.28.255.210",
        "status": "up",
        "protocol": "up",
        "operational": True,
        "label": ("GigabitEthernet0/0 - 172.28.255.210"),
    }


def test_parse_l3_interfaces_includes_operational_svis():
    result = parse_l3_interfaces(SHOW_IP_INTERFACE_BRIEF)

    vlan10 = next(item for item in result if item["name"] == "Vlan10")

    assert vlan10["ip_address"] == "192.168.10.254"
    assert vlan10["operational"] is True


def test_parse_l3_interfaces_preserves_down_interface():
    result = parse_l3_interfaces(SHOW_IP_INTERFACE_BRIEF)

    vlan50 = next(item for item in result if item["name"] == "Vlan50")

    assert vlan50["operational"] is False
    assert vlan50["status"] == "administratively down"
    assert vlan50["protocol"] == "down"


def test_parse_l3_interfaces_ignores_unassigned():
    result = parse_l3_interfaces(SHOW_IP_INTERFACE_BRIEF)

    names = {item["name"] for item in result}

    assert "GigabitEthernet0/1" not in names
    assert "GigabitEthernet0/2" not in names
    assert "Vlan100" not in names


def test_parse_single_ipv4_target():
    assert parse_ipv4_targets("8.8.8.8") == ["8.8.8.8"]


def test_parse_multiple_ipv4_targets():
    assert parse_ipv4_targets("8.8.8.8, 1.1.1.1") == [
        "8.8.8.8",
        "1.1.1.1",
    ]


def test_parse_ipv4_range():
    assert parse_ipv4_targets("192.168.10.1-192.168.10.4") == [
        "192.168.10.1",
        "192.168.10.2",
        "192.168.10.3",
        "192.168.10.4",
    ]


def test_parse_combined_targets_and_range():
    assert parse_ipv4_targets("8.8.8.8,192.168.10.1-192.168.10.3,1.1.1.1") == [
        "8.8.8.8",
        "192.168.10.1",
        "192.168.10.2",
        "192.168.10.3",
        "1.1.1.1",
    ]


def test_parse_targets_deduplicates_preserving_order():
    assert parse_ipv4_targets(
        "8.8.8.8,192.168.10.1-192.168.10.2,8.8.8.8,192.168.10.2"
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
        ("192.168.10.1-192.168.10.2-192.168.10.3"),
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


def test_find_l3_interface_case_insensitive():
    interfaces = parse_l3_interfaces(SHOW_IP_INTERFACE_BRIEF)

    result = find_l3_interface_by_name(
        interfaces,
        "gigabitethernet0/0",
    )

    assert result["ip_address"] == "172.28.255.210"


def test_validate_source_accepts_routed_physical_interface():
    interfaces = parse_l3_interfaces(SHOW_IP_INTERFACE_BRIEF)

    result = validate_source_interface(
        interfaces,
        "GigabitEthernet0/0",
    )

    assert result["operational"] is True
    assert result["ip_address"] == "172.28.255.210"


def test_validate_source_accepts_svi():
    interfaces = parse_l3_interfaces(SHOW_IP_INTERFACE_BRIEF)

    result = validate_source_interface(
        interfaces,
        "Vlan10",
    )

    assert result["operational"] is True


def test_validate_source_rejects_non_operational_interface():
    interfaces = parse_l3_interfaces(SHOW_IP_INTERFACE_BRIEF)

    with pytest.raises(
        ValueError,
        match="não está operacional",
    ):
        validate_source_interface(
            interfaces,
            "Vlan50",
        )


def test_validate_source_rejects_unknown_interface():
    interfaces = parse_l3_interfaces(SHOW_IP_INTERFACE_BRIEF)

    with pytest.raises(
        ValueError,
        match="não encontrada",
    ):
        validate_source_interface(
            interfaces,
            "Vlan999",
        )


def test_parse_ping_result_success():
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


def test_parse_targets_has_no_default_quantity_limit():
    targets = parse_ipv4_targets("10.10.0.1-10.10.0.100")

    assert len(targets) == 100
    assert targets[0] == "10.10.0.1"
    assert targets[-1] == "10.10.0.100"


def test_extract_traceroute_result_removes_interactive_dialog():
    from src.switch.troubleshooting import (
        extract_traceroute_result,
    )

    output = """\
traceroute
Protocol [ip]:
Target IP address: 8.8.8.8
Source address: 172.28.255.210
Numeric display [n]:
Timeout in seconds [3]:
Probe count [3]:
Minimum Time to Live [1]:
Maximum Time to Live [30]:
Port Number [33434]:
Loose, Strict, Record, Timestamp, Verbose[none]:
Type escape sequence to abort.
Tracing the route to 8.8.8.8
VRF info: (vrf in name/id, vrf out name/id)
  1 172.28.255.254 3 msec 1 msec 1 msec
  2  *  *  *
  3 201.1.233.93 3 msec 4 msec
 11 8.8.8.8 28 msec 24 msec 28 msec
SW-TESTE1#
"""

    result = extract_traceroute_result(output)

    assert result.startswith("VRF info:")

    assert "1 172.28.255.254" in result

    assert "11 8.8.8.8" in result

    assert "Protocol [ip]" not in result
    assert "Target IP address" not in result
    assert "SW-TESTE1#" not in result


def test_parse_targets_has_no_default_limit():
    targets = parse_ipv4_targets("10.10.0.1-10.10.0.100")

    assert len(targets) == 100
    assert targets[0] == "10.10.0.1"
    assert targets[-1] == "10.10.0.100"


def test_extract_traceroute_result_keeps_only_useful_output():
    from src.switch.troubleshooting import (
        extract_traceroute_result,
    )

    output = """\
traceroute
Protocol [ip]:
Target IP address: 8.8.8.8
Source address: 172.28.255.210
Numeric display [n]:
Timeout in seconds [3]:
Probe count [3]:
Minimum Time to Live [1]:
Maximum Time to Live [30]:
Port Number [33434]:
Loose, Strict, Record, Timestamp, Verbose[none]:
Type escape sequence to abort.
Tracing the route to 8.8.8.8
VRF info: (vrf in name/id, vrf out name/id)
  1 172.28.255.254 3 msec 1 msec 1 msec
  2  *  *  *
  3 201.1.233.93 3 msec 4 msec
 11 8.8.8.8 28 msec 24 msec 28 msec
SW-TESTE1#
"""

    result = extract_traceroute_result(output)

    assert result.startswith("VRF info:")

    assert "1 172.28.255.254" in result
    assert "11 8.8.8.8" in result

    assert "Protocol [ip]" not in result
    assert "Target IP address" not in result
    assert "SW-TESTE1#" not in result


def test_split_targets_balances_workers():
    from src.switch.troubleshooting import (
        split_targets_for_workers,
    )

    targets = [f"192.0.2.{value}" for value in range(1, 11)]

    result = split_targets_for_workers(
        targets,
        workers=4,
    )

    assert [len(chunk) for chunk in result] == [
        3,
        3,
        2,
        2,
    ]

    assert [target for chunk in result for target in chunk] == targets


def test_split_targets_never_creates_more_workers_than_targets():
    from src.switch.troubleshooting import (
        split_targets_for_workers,
    )

    result = split_targets_for_workers(
        ["192.0.2.1", "192.0.2.2"],
        workers=8,
    )

    assert len(result) == 2
