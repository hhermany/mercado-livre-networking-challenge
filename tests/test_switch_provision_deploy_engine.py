import pytest

from src.switch.cisco import CiscoSwitch


class FakeConnection:
    def __init__(
        self,
        *,
        outputs=None,
        running_config="",
    ):
        self.outputs = list(outputs or [])

        self.running_config = running_config

        self.sent_blocks = []
        self.show_commands = []

        self.enabled = False
        self.prompt_updates = 0

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        traceback,
    ):
        return False

    def enable(self):
        self.enabled = True

    def send_config_set(
        self,
        commands,
        **kwargs,
    ):
        self.sent_blocks.append(list(commands))

        if self.outputs:
            return self.outputs.pop(0)

        return ""

    def set_base_prompt(self):
        self.prompt_updates += 1

        return "SW"

    def send_command(
        self,
        command,
        **kwargs,
    ):
        self.show_commands.append(command)

        if command == "show running-config":
            return self.running_config

        raise AssertionError(f"Comando inesperado: {command}")


def build_switch(
    monkeypatch,
    connection,
    *,
    secret="",
):
    switch = CiscoSwitch(
        host="192.0.2.10",
        username="admin",
        password="password",
        secret=secret,
    )

    monkeypatch.setattr(
        switch,
        "_connect",
        lambda: connection,
    )

    return switch


def test_deploy_sends_candidate_block_by_block(
    monkeypatch,
):
    connection = FakeConnection(
        outputs=[
            "hostname SW-01",
            "aaa new-model",
            ("aaa group server radius RAD\nserver name RAD1\nserver name RAD2"),
        ],
        running_config=("hostname SW-01\naaa new-model\n"),
    )

    switch = build_switch(
        monkeypatch,
        connection,
    )

    result = switch.deploy_config(
        """
hostname SW-01
!
aaa new-model
!
aaa group server radius RAD
 server name RAD1
 server name RAD2
!
end
"""
    )

    assert connection.sent_blocks == [
        [
            "hostname SW-01",
        ],
        [
            "aaa new-model",
        ],
        [
            "aaa group server radius RAD",
            "server name RAD1",
            "server name RAD2",
        ],
    ]

    assert result["success"] is True
    assert result["blocks_sent"] == 3
    assert result["commands_sent"] == 5

    assert result["saved"] is False


def test_deploy_updates_prompt_after_hostname(
    monkeypatch,
):
    connection = FakeConnection(
        outputs=[
            "hostname SW-NEW",
            "aaa new-model",
        ],
        running_config=("hostname SW-NEW\naaa new-model\n"),
    )

    switch = build_switch(
        monkeypatch,
        connection,
    )

    switch.deploy_config(
        """
hostname SW-NEW
!
aaa new-model
!
"""
    )

    assert connection.prompt_updates == 1


def test_deploy_stops_on_invalid_input(
    monkeypatch,
):
    connection = FakeConnection(
        outputs=[
            "hostname SW-01",
            ("bad command\n% Invalid input detected at '^' marker."),
            "aaa new-model",
        ],
        running_config="",
    )

    switch = build_switch(
        monkeypatch,
        connection,
    )

    with pytest.raises(
        RuntimeError,
        match="Falha no bloco 2",
    ):
        switch.deploy_config(
            """
hostname SW-01
!
bad command
!
aaa new-model
!
"""
        )

    assert connection.sent_blocks == [
        [
            "hostname SW-01",
        ],
        [
            "bad command",
        ],
    ]

    assert "show running-config" not in connection.show_commands


def test_deploy_detects_incomplete_command(
    monkeypatch,
):
    connection = FakeConnection(
        outputs=[
            "% Incomplete command.",
        ],
    )

    switch = build_switch(
        monkeypatch,
        connection,
    )

    with pytest.raises(
        RuntimeError,
        match="Incomplete command",
    ):
        switch.deploy_config(
            """
radius server RAD1
!
"""
        )


def test_deploy_detects_ambiguous_command(
    monkeypatch,
):
    connection = FakeConnection(
        outputs=[
            "% Ambiguous command",
        ],
    )

    switch = build_switch(
        monkeypatch,
        connection,
    )

    with pytest.raises(
        RuntimeError,
        match="Ambiguous command",
    ):
        switch.deploy_config(
            """
some ambiguous command
!
"""
        )


def test_deploy_reads_running_config_after_success(
    monkeypatch,
):
    connection = FakeConnection(
        outputs=[
            "aaa new-model",
        ],
        running_config=("aaa new-model\n"),
    )

    switch = build_switch(
        monkeypatch,
        connection,
    )

    result = switch.deploy_config(
        """
aaa new-model
!
"""
    )

    assert connection.show_commands == ["show running-config"]

    assert result["running_config"] == "aaa new-model\n"


def test_deploy_enters_enable_when_secret_exists(
    monkeypatch,
):
    connection = FakeConnection(
        outputs=[
            "aaa new-model",
        ],
        running_config=("aaa new-model\n"),
    )

    switch = build_switch(
        monkeypatch,
        connection,
        secret="enable-secret",
    )

    switch.deploy_config(
        """
aaa new-model
!
"""
    )

    assert connection.enabled is True


def test_empty_candidate_is_rejected(
    monkeypatch,
):
    connection = FakeConnection()

    switch = build_switch(
        monkeypatch,
        connection,
    )

    with pytest.raises(
        ValueError,
        match="Candidate vazio",
    ):
        switch.deploy_config("!\n!\n")

    assert connection.sent_blocks == []


def test_deploy_does_not_save_startup_config(
    monkeypatch,
):
    connection = FakeConnection(
        outputs=[
            "hostname SW-01",
        ],
        running_config=("hostname SW-01\n"),
    )

    switch = build_switch(
        monkeypatch,
        connection,
    )

    result = switch.deploy_config(
        """
hostname SW-01
!
"""
    )

    all_commands = [command for block in connection.sent_blocks for command in block]

    assert "write memory" not in all_commands

    assert "copy running-config startup-config" not in all_commands

    assert result["saved"] is False
