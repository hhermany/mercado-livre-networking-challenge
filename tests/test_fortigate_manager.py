import src.devices.fortigate as fortigate_module
from src.devices.fortigate import (
    FortiGateDriver,
    discover_managed_fortigate,
)
from src.devices.fortigate_manager import (
    FortiGateManager,
)


def test_fortigate_manager_upsert_and_list():
    manager = FortiGateManager()

    device = manager.upsert(
        host="192.0.2.10",
        username="admin",
        password="password",
    )

    devices = manager.list()

    assert len(devices) == 1
    assert devices[0]["id"] == device.id
    assert devices[0]["host"] == "192.0.2.10"
    assert devices[0]["username"] == "admin"
    assert "password" not in devices[0]


def test_fortigate_manager_updates_existing_host():
    manager = FortiGateManager()

    first = manager.upsert(
        host="192.0.2.10",
        username="admin",
        password="old",
    )

    second = manager.upsert(
        host="192.0.2.10",
        username="automation",
        password="new",
    )

    assert first.id == second.id
    assert manager.get(first.id).username == "automation"
    assert manager.get(first.id).password == "new"


def test_fortigate_manager_remove():
    manager = FortiGateManager()

    device = manager.upsert(
        host="192.0.2.10",
        username="admin",
        password="password",
    )

    manager.remove(device.id)

    assert manager.list() == []


def test_fortigate_discovery(monkeypatch):
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(
            self,
            exc_type,
            exc_value,
            traceback,
        ):
            return False

        def send_command(self, command):
            assert command == "get system status"

            return """\
Version: FortiGate-VM64-KVM v7.2.8,build1639
Serial-Number: FGVMTEST123
Hostname: BRANCH-1
"""

    def fake_connect_handler(**kwargs):
        assert kwargs["device_type"] == "fortinet"
        assert kwargs["host"] == "192.0.2.10"
        return FakeConnection()

    monkeypatch.setattr(
        fortigate_module,
        "ConnectHandler",
        fake_connect_handler,
    )

    driver = FortiGateDriver(
        host="192.0.2.10",
        username="admin",
        password="password",
    )

    result = driver.discover()

    assert result["hostname"] == "BRANCH-1"
    assert "v7.2.8" in result["version"]
    assert result["serial"] == "FGVMTEST123"


def test_discover_managed_fortigate(monkeypatch):
    manager = FortiGateManager()

    device = manager.upsert(
        host="192.0.2.10",
        username="admin",
        password="password",
    )

    monkeypatch.setattr(
        FortiGateDriver,
        "discover",
        lambda self: {
            "hostname": "BRANCH-2",
            "version": "FortiOS 7.2.8",
            "serial": "FGVM2",
        },
    )

    result = discover_managed_fortigate(device)

    assert result["hostname"] == "BRANCH-2"
    assert result["serial"] == "FGVM2"


def test_fortigate_ipsec_capability_discovery(
    monkeypatch,
):
    outputs = {
        "set proposal ?": """\
des-md5       des-md5
des-sha1      des-sha1
des-sha256    des-sha256
des-sha384    des-sha384
des-sha512    des-sha512
""",
        "set dhgrp ?": """\
1
2
5
14
15
16
""",
        "set ike-version ?": """\
1
2
""",
    }

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(
            self,
            exc_type,
            exc_value,
            traceback,
        ):
            return False

        def send_command_timing(
            self,
            command,
            **kwargs,
        ):
            return outputs.get(
                command,
                "",
            )

    monkeypatch.setattr(
        fortigate_module,
        "ConnectHandler",
        lambda **kwargs: FakeConnection(),
    )

    driver = FortiGateDriver(
        host="192.0.2.10",
        username="admin",
        password="password",
    )

    result = driver.discover_ipsec_capabilities()

    assert result.ike_versions == (1, 2)

    assert result.phase1_proposals == (
        "des-md5",
        "des-sha1",
        "des-sha256",
        "des-sha384",
        "des-sha512",
    )

    assert result.phase1_dh_groups == (1, 2, 5, 14, 15, 16)

    assert result.phase2_proposals == result.phase1_proposals


def test_capability_parser_ignores_cli_noise():
    output = """\
des-sha1      des-sha1
des-sha256    des-sha256
incomplete
unknown
error
"""

    result = FortiGateDriver._parse_cli_choices(output)

    assert result == (
        "des-sha1",
        "des-sha256",
    )


def test_fortigate_manager_persistence_survives_restart(tmp_path):
    database_path = tmp_path / "fortigates.sqlite3"
    key_path = tmp_path / "fortigates.key"

    first_manager = FortiGateManager()
    first_manager.enable_persistence(
        database_path=database_path,
        key_path=key_path,
    )

    device = first_manager.upsert(
        host="192.0.2.10",
        username="admin",
        password="secret-password",
    )

    original_id = device.id

    second_manager = FortiGateManager()
    second_manager.enable_persistence(
        database_path=database_path,
        key_path=key_path,
    )

    devices = second_manager.list()

    assert len(devices) == 1
    assert devices[0]["id"] == original_id
    assert devices[0]["host"] == "192.0.2.10"
    assert devices[0]["username"] == "admin"
    assert "password" not in devices[0]

    restored = second_manager.get(original_id)

    assert restored.password == "secret-password"


def test_fortigate_manager_persistence_updates_credentials(tmp_path):
    database_path = tmp_path / "fortigates.sqlite3"
    key_path = tmp_path / "fortigates.key"

    manager = FortiGateManager()
    manager.enable_persistence(
        database_path=database_path,
        key_path=key_path,
    )

    first = manager.upsert(
        host="192.0.2.10",
        username="admin",
        password="old-password",
    )

    second = manager.upsert(
        host="192.0.2.10",
        username="automation",
        password="new-password",
    )

    assert first.id == second.id

    restarted = FortiGateManager()
    restarted.enable_persistence(
        database_path=database_path,
        key_path=key_path,
    )

    restored = restarted.get(first.id)

    assert restored.username == "automation"
    assert restored.password == "new-password"


def test_fortigate_manager_persistence_remove_survives_restart(tmp_path):
    database_path = tmp_path / "fortigates.sqlite3"
    key_path = tmp_path / "fortigates.key"

    manager = FortiGateManager()
    manager.enable_persistence(
        database_path=database_path,
        key_path=key_path,
    )

    device = manager.upsert(
        host="192.0.2.10",
        username="admin",
        password="password",
    )

    manager.remove(device.id)

    restarted = FortiGateManager()
    restarted.enable_persistence(
        database_path=database_path,
        key_path=key_path,
    )

    assert restarted.list() == []


def test_fortigate_manager_persists_discovered_state(tmp_path):
    database_path = tmp_path / "fortigates.sqlite3"
    key_path = tmp_path / "fortigates.key"

    manager = FortiGateManager()
    manager.enable_persistence(
        database_path=database_path,
        key_path=key_path,
    )

    device = manager.upsert(
        host="192.0.2.10",
        username="admin",
        password="password",
    )

    device.hostname = "FW-BRANCH-1"
    device.status = "connected"
    device.error = None

    manager.save(device)

    restarted = FortiGateManager()
    restarted.enable_persistence(
        database_path=database_path,
        key_path=key_path,
    )

    restored = restarted.get(device.id)

    assert restored.hostname == "FW-BRANCH-1"
    assert restored.status == "connected"
    assert restored.username == "admin"
    assert restored.password == "password"
