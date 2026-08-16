import pytest

import src.devices.fortigate as fortigate


class FakeConnection:
    def __init__(
        self,
        outputs,
    ):
        self.outputs = outputs

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        traceback,
    ):
        return False

    def send_command(
        self,
        command,
        **kwargs,
    ):
        return self.outputs[command]


def good_outputs():
    return {
        "show system interface": """
config system interface
    edit "port4"
        set ip 10.0.1.254 255.255.255.0
    next
    edit "VPN1-PA-DC"
        set ip 169.255.0.2 255.255.255.255
    next
    edit "VPN2-PA-DC"
        set ip 169.255.0.6 255.255.255.255
    next
    edit "LO-MGMT"
        set ip 172.31.255.2 255.255.255.255
    next
end
""",
        "show system dhcp server": """
config system dhcp server
    edit 2
        set default-gateway 10.0.1.254
        set interface "port4"
        config ip-range
            edit 1
                set start-ip 10.0.1.1
                set end-ip 10.0.1.10
            next
        end
        set dns-server1 10.255.255.1
    next
end
""",
        "get vpn ipsec tunnel summary": """
'VPN1-PA-DC' 100.64.0.1:0 selectors(total,up): 1/1 rx(pkt,err): 10/0 tx(pkt,err): 10/0
'VPN2-PA-DC' 100.100.0.1:0 selectors(total,up): 1/1 rx(pkt,err): 10/0 tx(pkt,err): 10/0
""",
        "get router info bgp summary": """
Neighbor     V     AS MsgRcvd MsgSent TblVer InQ OutQ Up/Down State/PfxRcd
169.255.0.1  4  65001      20      20      2   0    0 00:05:00 1
169.255.0.5  4  65001      20      20      2   0    0 00:05:00 1
""",
        "get router info routing-table all": (
            "B 10.255.255.0/24 [200/0] via 169.255.0.1 "
            "(recursive via VPN1-PA-DC tunnel 100.64.0.1)\n"
            "[200/0] via 169.255.0.5 "
            "(recursive via VPN2-PA-DC tunnel 100.100.0.1)"
        ),
        "diagnose sys sdwan health-check": """
Health Check(SLA_DC):
Seq(1 VPN1-PA-DC): state(alive), packet-loss(0.000%) latency(4.1)
Seq(2 VPN2-PA-DC): state(alive), packet-loss(0.000%) latency(4.2)
""",
    }


def driver():
    return fortigate.FortiGateDriver(
        host="192.0.2.20",
        username="admin",
        password="password",
    )


def validate(instance):
    return instance.validate_operational_state(
        expected_lan_gateway="10.0.1.254",
        expected_loopback_ip="172.31.255.2",
        expected_vpn1_fg_ip="169.255.0.2",
        expected_vpn2_fg_ip="169.255.0.6",
        expected_bgp_neighbors=(
            "169.255.0.1",
            "169.255.0.5",
        ),
        expected_dhcp_start="10.0.1.1",
        expected_dhcp_end="10.0.1.10",
        attempts=1,
        interval=0,
    )


def test_operational_validation_success(
    monkeypatch,
):
    outputs = good_outputs()

    monkeypatch.setattr(
        fortigate,
        "ConnectHandler",
        lambda **kwargs: FakeConnection(outputs),
    )

    assert validate(driver()) is True


def test_operational_validation_detects_vpn_down(
    monkeypatch,
):
    outputs = good_outputs()

    outputs["get vpn ipsec tunnel summary"] = outputs[
        "get vpn ipsec tunnel summary"
    ].replace(
        "selectors(total,up): 1/1",
        "selectors(total,up): 1/0",
        1,
    )

    monkeypatch.setattr(
        fortigate,
        "ConnectHandler",
        lambda **kwargs: FakeConnection(outputs),
    )

    with pytest.raises(
        RuntimeError,
        match="VPN1 IPsec UP",
    ):
        validate(driver())


def test_operational_validation_detects_dhcp_missing(
    monkeypatch,
):
    outputs = good_outputs()

    outputs["show system dhcp server"] = ""

    monkeypatch.setattr(
        fortigate,
        "ConnectHandler",
        lambda **kwargs: FakeConnection(outputs),
    )

    with pytest.raises(
        RuntimeError,
        match="DHCP interface port4",
    ):
        validate(driver())


def test_operational_validation_accepts_golden_legacy_vpn1_name(
    monkeypatch,
):
    outputs = good_outputs()

    for command in (
        "get vpn ipsec tunnel summary",
        "get router info routing-table all",
        "diagnose sys sdwan health-check",
    ):
        outputs[command] = outputs[command].replace(
            "VPN1-PA-DC",
            "VPN-PA-DC",
        )

    monkeypatch.setattr(
        fortigate,
        "ConnectHandler",
        lambda **kwargs: FakeConnection(outputs),
    )

    instance = driver()

    result = instance.validate_operational_state(
        expected_lan_gateway="10.0.1.254",
        expected_loopback_ip="172.31.255.2",
        expected_vpn1_fg_ip="169.255.0.2",
        expected_vpn2_fg_ip="169.255.0.6",
        expected_bgp_neighbors=(
            "169.255.0.1",
            "169.255.0.5",
        ),
        expected_dhcp_start="10.0.1.1",
        expected_dhcp_end="10.0.1.10",
        expected_vpn_names=(
            "VPN-PA-DC",
            "VPN2-PA-DC",
        ),
        attempts=1,
        interval=0,
    )

    assert result is True
