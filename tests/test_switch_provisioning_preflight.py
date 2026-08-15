import pytest

import src.switch.provisioning.preflight as preflight


class FakeConnection:
    def __init__(
        self,
        *,
        responses,
    ):
        self.responses = responses
        self.commands = []
        self.enabled = False
        self.disconnected = False

    def enable(self):
        self.enabled = True

    def send_command_timing(
        self,
        command,
        **kwargs,
    ):
        self.commands.append(command)

        return self.responses.get(
            command,
            "",
        )

    def disconnect(self):
        self.disconnected = True


def test_incomplete_command_means_supported():
    assert preflight._command_is_supported("% Incomplete command.")


def test_invalid_input_means_unsupported():
    assert not preflight._command_is_supported(
        "% Invalid input detected at '^' marker."
    )


def test_detects_ip_domain_name_syntax(
    monkeypatch,
):
    connection = FakeConnection(
        responses={
            "configure terminal": "",
            "ip domain name": "% Incomplete command.",
            "end": "",
        }
    )

    monkeypatch.setattr(
        preflight,
        "ConnectHandler",
        lambda **kwargs: connection,
    )

    result = preflight.detect_provision_capabilities(
        host="192.0.2.1",
        username="admin",
        password="password",
    )

    assert result.domain_command == "ip domain name"

    assert result.domain_syntax == "ios_xe_style"

    assert "ip domain-name" not in connection.commands

    assert connection.disconnected


def test_falls_back_to_domain_name_with_hyphen(
    monkeypatch,
):
    connection = FakeConnection(
        responses={
            "configure terminal": "",
            "ip domain name": "% Invalid input detected",
            "ip domain-name": "% Incomplete command.",
            "end": "",
        }
    )

    monkeypatch.setattr(
        preflight,
        "ConnectHandler",
        lambda **kwargs: connection,
    )

    result = preflight.detect_provision_capabilities(
        host="192.0.2.2",
        username="admin",
        password="password",
    )

    assert result.domain_command == "ip domain-name"

    assert result.domain_syntax == "classic_style"

    assert connection.commands == [
        "configure terminal",
        "ip domain name",
        "ip domain-name",
        "service unsupported-transceiver ?",
        "platform punt-keepalive ?",
        "transceiver type ?",
        "end",
    ]

    assert connection.disconnected


def test_preflight_fails_when_neither_syntax_exists(
    monkeypatch,
):
    connection = FakeConnection(
        responses={
            "configure terminal": "",
            "ip domain name": "% Invalid input detected",
            "ip domain-name": "% Invalid input detected",
            "end": "",
        }
    )

    monkeypatch.setattr(
        preflight,
        "ConnectHandler",
        lambda **kwargs: connection,
    )

    with pytest.raises(
        RuntimeError,
        match=("Nenhuma sintaxe suportada"),
    ):
        preflight.detect_provision_capabilities(
            host="192.0.2.3",
            username="admin",
            password="password",
        )

    assert connection.disconnected


def test_preflight_enters_enable_when_secret_exists(
    monkeypatch,
):
    connection = FakeConnection(
        responses={
            "configure terminal": "",
            "ip domain name": "% Incomplete command.",
            "end": "",
        }
    )

    monkeypatch.setattr(
        preflight,
        "ConnectHandler",
        lambda **kwargs: connection,
    )

    preflight.detect_provision_capabilities(
        host="192.0.2.4",
        username="admin",
        password="password",
        secret="enable-secret",
    )

    assert connection.enabled


def test_probe_never_sends_real_domain_configuration(
    monkeypatch,
):
    connection = FakeConnection(
        responses={
            "configure terminal": "",
            "ip domain name": "% Incomplete command.",
            "end": "",
        }
    )

    monkeypatch.setattr(
        preflight,
        "ConnectHandler",
        lambda **kwargs: connection,
    )

    preflight.detect_provision_capabilities(
        host="192.0.2.5",
        username="admin",
        password="password",
    )

    assert "ip domain name MercadoLivre.local" not in connection.commands

    assert "ip domain-name MercadoLivre.local" not in connection.commands


def test_detects_optional_capabilities(
    monkeypatch,
):
    connection = FakeConnection(
        responses={
            "configure terminal": "",
            "ip domain name": "% Invalid input detected",
            "ip domain-name": "% Incomplete command.",
            "service unsupported-transceiver ?": "% Invalid input detected",
            "platform punt-keepalive ?": "% Invalid input detected",
            "transceiver type ?": "all  Monitor all transceivers",
            "end": "",
        }
    )

    monkeypatch.setattr(
        preflight,
        "ConnectHandler",
        lambda **kwargs: connection,
    )

    result = preflight.detect_provision_capabilities(
        host="192.0.2.20",
        username="admin",
        password="password",
    )

    assert result.unsupported_transceiver is False

    assert result.platform_punt_keepalive is False

    assert result.transceiver_monitoring is True
