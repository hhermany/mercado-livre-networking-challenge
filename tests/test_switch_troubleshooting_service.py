import src.switch.service as service


class FakeTroubleshootingSwitch:
    def __init__(self, **kwargs):
        pass

    def list_svis(self):
        return {
            "svis": [
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

    def traceroute(
        self,
        destination,
        source_ip,
    ):
        return {
            "mode": "extended",
            "destination": destination,
            "source_ip": source_ip,
            "output": (
                "Tracing the route to "
                f"{destination}\n"
                "  1 192.168.10.1 1 msec"
            ),
        }


def test_get_switch_svis(monkeypatch):
    monkeypatch.setattr(
        service,
        "CiscoSwitch",
        FakeTroubleshootingSwitch,
    )

    result = service.get_switch_svis(
        host="192.0.2.1",
        username="admin",
        password="password",
    )

    assert len(result["svis"]) == 2


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


def test_run_switch_traceroute(
    monkeypatch,
):
    monkeypatch.setattr(
        service,
        "CiscoSwitch",
        FakeTroubleshootingSwitch,
    )

    result = service.run_switch_traceroute(
        host="192.0.2.1",
        username="admin",
        password="password",
        source_interface="Vlan10",
        destination="8.8.8.8",
    )

    assert result["destination"] == "8.8.8.8"
    assert result["source_interface"] == "Vlan10"
    assert result["source_ip"] == "192.168.10.254"
    assert result["mode"] == "extended"
    assert "Tracing the route" in result["output"]


def test_traceroute_uses_svi_ip_as_extended_source(
    monkeypatch,
):
    captured = {}

    class CapturingSwitch(
        FakeTroubleshootingSwitch
    ):
        def traceroute(
            self,
            destination,
            source_ip,
        ):
            captured["destination"] = destination
            captured["source_ip"] = source_ip

            return {
                "mode": "extended",
                "destination": destination,
                "source_ip": source_ip,
                "output": (
                    "Tracing the route to "
                    f"{destination}"
                ),
            }

    monkeypatch.setattr(
        service,
        "CiscoSwitch",
        CapturingSwitch,
    )

    service.run_switch_traceroute(
        host="192.0.2.1",
        username="admin",
        password="password",
        source_interface="Vlan10",
        destination="8.8.8.8",
    )

    assert captured == {
        "destination": "8.8.8.8",
        "source_ip": "192.168.10.254",
    }
