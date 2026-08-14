import time

import pytest

from src.switch.devices import (
    DeviceManager,
)


def test_add_device_does_not_expose_password():
    manager = DeviceManager()

    device = manager.add(
        host="192.0.2.10",
        username="admin",
        password="secret",
    )

    public = device.public()

    assert public["host"] == "192.0.2.10"
    assert "password" not in public
    assert "secret" not in public


def test_rejects_duplicate_host():
    manager = DeviceManager()

    manager.add(
        host="192.0.2.10",
        username="admin",
        password="secret",
    )

    with pytest.raises(
        ValueError,
        match="já está cadastrado",
    ):
        manager.add(
            host="192.0.2.10",
            username="admin",
            password="other",
        )


def test_remove_device():
    manager = DeviceManager()

    device = manager.add(
        host="192.0.2.10",
        username="admin",
        password="secret",
    )

    manager.remove(
        device.id
    )

    assert manager.list() == []


def test_parallel_discovery():
    manager = DeviceManager(
        max_workers=2
    )

    first = manager.add(
        host="192.0.2.10",
        username="admin",
        password="secret",
    )

    second = manager.add(
        host="192.0.2.11",
        username="admin",
        password="secret",
    )

    def discover(device):
        time.sleep(0.1)

        return {
            "hostname": (
                "SW1"
                if device.host.endswith(
                    ".10"
                )
                else "SW2"
            ),
            "interfaces": [],
        }

    started = time.monotonic()

    results = manager.discover_many(
        discover,
        device_ids=[
            first.id,
            second.id,
        ],
    )

    elapsed = (
        time.monotonic()
        - started
    )

    assert len(results) == 2

    assert all(
        item["success"]
        for item in results
    )

    # Duas chamadas de 100 ms devem executar
    # simultaneamente, não sequencialmente.
    assert elapsed < 0.19


def test_device_failure_is_isolated():
    manager = DeviceManager(
        max_workers=2
    )

    first = manager.add(
        host="192.0.2.10",
        username="admin",
        password="secret",
    )

    second = manager.add(
        host="192.0.2.11",
        username="admin",
        password="secret",
    )

    def discover(device):
        if device.id == second.id:
            raise RuntimeError(
                "SSH timeout"
            )

        return {
            "hostname": "SW1",
            "interfaces": [],
        }

    results = manager.discover_many(
        discover,
        device_ids=[
            first.id,
            second.id,
        ],
    )

    success = [
        item
        for item in results
        if item["success"]
    ]

    failures = [
        item
        for item in results
        if not item["success"]
    ]

    assert len(success) == 1
    assert len(failures) == 1

    assert (
        failures[0]["error"]
        == "SSH timeout"
    )
