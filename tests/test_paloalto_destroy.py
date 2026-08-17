import pytest

import src.devices.paloalto_manager as module
from src.devices.paloalto_manager import (
    PaloAltoManager,
)


class FakeConnection:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.commands = []
        self.commit_commands = []
        self.config_mode_called = False
        self.exit_config_mode_called = False

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        traceback,
    ):
        return False

    def config_mode(self):
        self.config_mode_called = True

    def send_config_set(
        self,
        commands,
        **kwargs,
    ):
        self.commands = list(commands)
        return "configuration deleted successfully"

    def send_command_timing(
        self,
        command,
        **kwargs,
    ):
        self.commit_commands.append(command)
        return "Commit job enqueued"

    def check_config_mode(self):
        return True

    def exit_config_mode(self):
        self.exit_config_mode_called = True


def test_cleanup_commands_accept_only_delete():
    commands = PaloAltoManager._cleanup_commands(
        """
        delete network tunnel ipsec BRANCH-2-VPN1
        delete network ike gateway BRANCH-2-VPN1
        """
    )

    assert commands == [
        "delete network tunnel ipsec BRANCH-2-VPN1",
        "delete network ike gateway BRANCH-2-VPN1",
    ]


def test_cleanup_commands_reject_set():
    with pytest.raises(
        ValueError,
        match="delete",
    ):
        PaloAltoManager._cleanup_commands(
            "set network tunnel ipsec BRANCH-2-VPN1"
        )


def test_cleanup_commands_reject_empty():
    with pytest.raises(
        ValueError,
        match="vazio",
    ):
        PaloAltoManager._cleanup_commands("")


def test_destroy_configuration_sends_delete_and_commit(
    monkeypatch,
):
    connection = FakeConnection()

    monkeypatch.setattr(
        module,
        "ConnectHandler",
        lambda **kwargs: connection,
    )

    manager = PaloAltoManager(
        host="192.0.2.10",
        username="admin",
        password="password",
    )

    result = manager.destroy_configuration(
        """
        delete network virtual-router default protocol bgp
        delete network tunnel ipsec BRANCH-2-VPN1
        """
    )

    assert connection.config_mode_called is True

    assert connection.commands == [
        "delete network virtual-router default protocol bgp",
        "delete network tunnel ipsec BRANCH-2-VPN1",
    ]

    assert connection.commit_commands == [
        "commit",
    ]

    assert connection.exit_config_mode_called is True

    assert "configuration" in result
    assert "commit" in result


def test_destroy_configuration_detects_panos_error(
    monkeypatch,
):
    class ErrorConnection(FakeConnection):
        def send_config_set(
            self,
            commands,
            **kwargs,
        ):
            return "Error: object not found"

    monkeypatch.setattr(
        module,
        "ConnectHandler",
        lambda **kwargs: ErrorConnection(),
    )

    manager = PaloAltoManager(
        host="192.0.2.10",
        username="admin",
        password="password",
    )

    with pytest.raises(
        RuntimeError,
        match="rejeitou",
    ):
        manager.destroy_configuration(
            "delete network tunnel ipsec BRANCH-2-VPN1"
        )
