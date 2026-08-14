import src.switch.service as service


class FakeTroubleshootingSwitch:
    def __init__(self, **kwargs):
        pass

    def list_l3_interfaces(self):
        return {
            "interfaces": [
                {
                    "name": "GigabitEthernet0/0",
                    "ip_address": "172.28.255.210",
                    "status": "up",
                    "protocol": "up",
                    "operational": True,
                    "label": (
                        "GigabitEthernet0/0 - "
                        "172.28.255.210"
                    ),
                },
                {
                    "name": "Vlan10",
                    "ip_address": "192.168.10.254",
                    "status": "up",
                    "protocol": "up",
                    "operational": True,
                    "label": "Vlan10 - 192.168.10.254",
                },
                {
                    "name": "Vlan50",
                    "ip_address": "192.168.50.254",
                    "status": "administratively down",
                    "protocol": "down",
                    "operational": False,
                    "label": "Vlan50 - 192.168.50.254",
                },
            ],
            "raw": "",
        }

    def ping(
        self,
        destination,
        source_interface,
        repeat=5,
        timeout=2,
        size=100,
        df_bit=False,
    ):
        return {
            "command": (
                f"ping {destination} "
                f"source {source_interface} "
                f"repeat {repeat} timeout {timeout}"
            ),
            "output": (
                "Success rate is 100 percent (5/5), "
                "round-trip min/avg/max = 1/2/3 ms"
            ),
        }

    def ping_many(
        self,
        destinations,
        source_interface,
        repeat=5,
        timeout=2,
        size=100,
        df_bit=False,
    ):
        return [
            self.ping(
                destination=destination,
                source_interface=source_interface,
                repeat=repeat,
                timeout=timeout,
                size=size,
                df_bit=df_bit,
            )
            | {
                "destination": destination,
            }
            for destination in destinations
        ]


    def traceroute(
        self,
        destination,
        source_ip,
        timeout=1,
        probe_count=3,
        max_ttl=20,
    ):
        return {
            "mode": "extended",
            "destination": destination,
            "source_ip": source_ip,
            "timeout": timeout,
            "probe_count": probe_count,
            "max_ttl": max_ttl,
            "output": (
                "Tracing the route to "
                f"{destination}\n"
                "  1 192.168.10.1 1 msec"
            ),
        }


def test_get_switch_l3_interfaces(monkeypatch):
    monkeypatch.setattr(
        service,
        "CiscoSwitch",
        FakeTroubleshootingSwitch,
    )

    result = service.get_switch_l3_interfaces(
        host="192.0.2.1",
        username="admin",
        password="password",
    )

    assert len(result["interfaces"]) >= 2


def test_run_switch_ping_multiple_targets(
    monkeypatch,
):
    monkeypatch.setattr(
        service,
        "CiscoSwitch",
        FakeTroubleshootingSwitch,
    )

    result = service.run_switch_ping(
        host="192.0.2.1",
        username="admin",
        password="password",
        source_interface="Vlan10",
        targets=(
            "8.8.8.8,"
            "192.168.20.1-192.168.20.2"
        ),
    )

    assert result["count"] == 3
    assert [
        item["destination"]
        for item in result["results"]
    ] == [
        "8.8.8.8",
        "192.168.20.1",
        "192.168.20.2",
    ]

    assert all(
        item["success"] is True
        for item in result["results"]
    )


def test_run_switch_ping_rejects_down_source(
    monkeypatch,
):
    monkeypatch.setattr(
        service,
        "CiscoSwitch",
        FakeTroubleshootingSwitch,
    )

    try:
        service.run_switch_ping(
            host="192.0.2.1",
            username="admin",
            password="password",
            source_interface="Vlan50",
            targets="8.8.8.8",
        )
    except ValueError as exc:
        assert "não está operacional" in str(exc)
    else:
        raise AssertionError(
            "ValueError esperado"
        )


def test_traceroute_uses_interface_ip_as_extended_source(
    monkeypatch,
):
    captured = {}

    class CapturingSwitch:
        def __init__(self, **kwargs):
            pass

        def list_l3_interfaces(self):
            return {
                "interfaces": [
                    {
                        "name": "GigabitEthernet0/0",
                        "ip_address": "172.28.255.210",
                        "status": "up",
                        "protocol": "up",
                        "operational": True,
                        "label": (
                            "GigabitEthernet0/0 - "
                            "172.28.255.210"
                        ),
                    }
                ],
                "raw": "",
            }

        def traceroute(
            self,
            destination,
            source_ip,
            timeout=1,
            probe_count=3,
            max_ttl=20,
        ):
            captured.update(
                {
                    "destination": destination,
                    "source_ip": source_ip,
                    "timeout": timeout,
                    "probe_count": probe_count,
                    "max_ttl": max_ttl,
                }
            )

            return {
                "mode": "extended",
                "destination": destination,
                "source_ip": source_ip,
                "timeout": timeout,
                "probe_count": probe_count,
                "max_ttl": max_ttl,
                "output": (
                    "Tracing the route to "
                    f"{destination}\n"
                    "VRF info: "
                    "(vrf in name/id, vrf out name/id)\n"
                    "  1 172.28.255.254 1 msec\n"
                ),
            }

    monkeypatch.setattr(
        service,
        "CiscoSwitch",
        CapturingSwitch,
    )

    result = service.run_switch_traceroute(
        host="192.0.2.1",
        username="admin",
        password="password",
        source_interface="GigabitEthernet0/0",
        destination="8.8.8.8",
        timeout=1,
        probe_count=1,
        max_ttl=15,
    )

    assert captured == {
        "destination": "8.8.8.8",
        "source_ip": "172.28.255.210",
        "timeout": 1,
        "probe_count": 1,
        "max_ttl": 15,
    }

    assert (
        result["source_interface"]
        == "GigabitEthernet0/0"
    )

    assert (
        result["source_ip"]
        == "172.28.255.210"
    )




def test_run_switch_ping_accepts_routed_physical_source(
    monkeypatch,
):
    monkeypatch.setattr(
        service,
        "CiscoSwitch",
        FakeTroubleshootingSwitch,
    )

    result = service.run_switch_ping(
        host="192.0.2.1",
        username="admin",
        password="password",
        source_interface="GigabitEthernet0/0",
        targets="8.8.8.8",
        repeat=2,
    )

    assert (
        result["source"]["name"]
        == "GigabitEthernet0/0"
    )

    assert (
        result["source"]["ip_address"]
        == "172.28.255.210"
    )
def test_ping_batch_partitions_targets_across_workers(
    monkeypatch,
):
    calls = []

    class BatchSwitch(
        FakeTroubleshootingSwitch
    ):
        def ping_many(
            self,
            destinations,
            source_interface,
            repeat=5,
            timeout=2,
            size=100,
            df_bit=False,
        ):
            calls.append(
                list(destinations)
            )

            return [
                {
                    "destination": destination,
                    "command": (
                        f"ping {destination}"
                    ),
                    "output": (
                        "Success rate is 100 percent "
                        "(1/1), round-trip "
                        "min/avg/max = 1/1/1 ms"
                    ),
                }
                for destination in destinations
            ]

    monkeypatch.setattr(
        service,
        "CiscoSwitch",
        BatchSwitch,
    )

    result = service.run_switch_ping(
        host="192.0.2.1",
        username="admin",
        password="password",
        source_interface="Vlan10",
        targets="10.0.0.1-10.0.0.100",
        repeat=1,
        timeout=1,
        concurrency=4,
    )

    assert result["count"] == 100
    assert result["concurrency"] == 4

    assert len(calls) == 4

    assert sorted(
        len(batch)
        for batch in calls
    ) == [
        25,
        25,
        25,
        25,
    ]

    tested_targets = {
        target
        for batch in calls
        for target in batch
    }

    assert len(tested_targets) == 100

    assert [
        item["destination"]
        for item in result["results"]
    ] == [
        f"10.0.0.{value}"
        for value in range(1, 101)
    ]


def test_ping_batch_partitions_work_across_workers(
    monkeypatch,
):
    calls = []

    class ParallelSwitch:
        def __init__(self, **kwargs):
            pass

        def list_l3_interfaces(self):
            return {
                "interfaces": [
                    {
                        "name": "Vlan10",
                        "ip_address": "192.168.10.254",
                        "status": "up",
                        "protocol": "up",
                        "operational": True,
                        "label": (
                            "Vlan10 - 192.168.10.254"
                        ),
                    }
                ],
                "raw": "",
            }

        def ping_many(
            self,
            destinations,
            source_interface,
            repeat=5,
            timeout=2,
            size=100,
            df_bit=False,
        ):
            batch = list(destinations)

            calls.append(batch)

            return [
                {
                    "destination": destination,
                    "command": (
                        f"ping {destination}"
                    ),
                    "output": (
                        "Success rate is 100 percent "
                        "(1/1), round-trip "
                        "min/avg/max = 1/1/1 ms"
                    ),
                }
                for destination in batch
            ]

    monkeypatch.setattr(
        service,
        "CiscoSwitch",
        ParallelSwitch,
    )

    result = service.run_switch_ping(
        host="192.0.2.1",
        username="admin",
        password="password",
        source_interface="Vlan10",
        targets="10.0.0.1-10.0.0.100",
        repeat=1,
        timeout=1,
        concurrency=4,
    )

    assert result["count"] == 100
    assert result["concurrency"] == 4

    # 100 destinos / 4 workers =
    # 4 lotes de 25 destinos.
    assert len(calls) == 4

    assert sorted(
        len(batch)
        for batch in calls
    ) == [
        25,
        25,
        25,
        25,
    ]

    # Nenhum endereço perdido ou duplicado.
    tested = [
        target
        for batch in calls
        for target in batch
    ]

    assert len(tested) == 100
    assert len(set(tested)) == 100

    # O resultado entregue ao usuário
    # continua em ordem.
    assert [
        item["destination"]
        for item in result["results"]
    ] == [
        f"10.0.0.{value}"
        for value in range(
            1,
            101,
        )
    ]


def test_ping_range_larger_than_64_is_allowed(
    monkeypatch,
):
    monkeypatch.setattr(
        service,
        "CiscoSwitch",
        FakeTroubleshootingSwitch,
    )

    result = service.run_switch_ping(
        host="192.0.2.1",
        username="admin",
        password="password",
        source_interface="Vlan10",
        targets="10.0.0.1-10.0.0.100",
        repeat=1,
        timeout=1,
    )

    assert result["count"] == 100


def test_parallel_ping_preserves_target_order(
    monkeypatch,
):
    monkeypatch.setattr(
        service,
        "CiscoSwitch",
        FakeTroubleshootingSwitch,
    )

    result = service.run_switch_ping(
        host="192.0.2.1",
        username="admin",
        password="password",
        source_interface="Vlan10",
        targets="10.0.0.1-10.0.0.20",
        repeat=1,
        timeout=1,
        concurrency=4,
    )

    assert result["count"] == 20

    assert [
        item["destination"]
        for item in result["results"]
    ] == [
        f"10.0.0.{value}"
        for value in range(1, 21)
    ]

    assert result["concurrency"] == 4


def test_parallel_ping_caps_concurrency_at_target_count(
    monkeypatch,
):
    monkeypatch.setattr(
        service,
        "CiscoSwitch",
        FakeTroubleshootingSwitch,
    )

    result = service.run_switch_ping(
        host="192.0.2.1",
        username="admin",
        password="password",
        source_interface="Vlan10",
        targets="10.0.0.1,10.0.0.2",
        repeat=1,
        timeout=1,
        concurrency=8,
    )

    assert result["concurrency"] == 2


def test_parallel_ping_rejects_more_than_eight_workers(
    monkeypatch,
):
    import pytest

    monkeypatch.setattr(
        service,
        "CiscoSwitch",
        FakeTroubleshootingSwitch,
    )

    with pytest.raises(
        ValueError,
        match="entre 1 e 8",
    ):
        service.run_switch_ping(
            host="192.0.2.1",
            username="admin",
            password="password",
            source_interface="Vlan10",
            targets="10.0.0.1",
            concurrency=9,
        )
def test_run_switch_traceroute(
    monkeypatch,
):
    class TraceSwitch:
        def __init__(self, **kwargs):
            pass

        def list_l3_interfaces(self):
            return {
                "interfaces": [
                    {
                        "name": "Vlan10",
                        "ip_address": "192.168.10.254",
                        "status": "up",
                        "protocol": "up",
                        "operational": True,
                        "label": (
                            "Vlan10 - 192.168.10.254"
                        ),
                    }
                ],
                "raw": "",
            }

        def traceroute(
            self,
            destination,
            source_ip,
            timeout=1,
            probe_count=3,
            max_ttl=20,
        ):
            return {
                "mode": "extended",
                "destination": destination,
                "source_ip": source_ip,
                "timeout": timeout,
                "probe_count": probe_count,
                "max_ttl": max_ttl,
                "output": (
                    "traceroute\n"
                    "Protocol [ip]:\n"
                    f"Target IP address: {destination}\n"
                    f"Source address: {source_ip}\n"
                    "Numeric display [n]:\n"
                    "Timeout in seconds [3]:\n"
                    "Probe count [3]:\n"
                    "Minimum Time to Live [1]:\n"
                    "Maximum Time to Live [30]:\n"
                    "Port Number [33434]:\n"
                    "Loose, Strict, Record, "
                    "Timestamp, Verbose[none]:\n"
                    "Type escape sequence to abort.\n"
                    f"Tracing the route to {destination}\n"
                    "VRF info: "
                    "(vrf in name/id, vrf out name/id)\n"
                    "  1 192.168.10.1 1 msec\n"
                    "  2 8.8.8.8 2 msec\n"
                ),
            }

    monkeypatch.setattr(
        service,
        "CiscoSwitch",
        TraceSwitch,
    )

    result = service.run_switch_traceroute(
        host="192.0.2.1",
        username="admin",
        password="password",
        source_interface="Vlan10",
        destination="8.8.8.8",
        timeout=1,
        probe_count=2,
        max_ttl=20,
    )

    assert result["destination"] == "8.8.8.8"
    assert result["source_interface"] == "Vlan10"
    assert result["source_ip"] == "192.168.10.254"

    assert result["mode"] == "extended"
    assert result["timeout"] == 1
    assert result["probe_count"] == 2
    assert result["max_ttl"] == 20

    # Output mostrado ao operador.
    assert result["output"].startswith(
        "VRF info:"
    )

    assert "192.168.10.1" in result["output"]
    assert "8.8.8.8" in result["output"]

    assert "Protocol [ip]" not in result["output"]
    assert "Target IP address" not in result["output"]

    # Sessão completa continua disponível
    # para diagnóstico da própria automação.
    assert "Protocol [ip]" in result["raw_output"]
    assert "Target IP address" in result["raw_output"]
