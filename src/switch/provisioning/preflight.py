from dataclasses import dataclass

from netmiko import ConnectHandler

INVALID_MARKERS = (
    "% invalid input",
    "% ambiguous command",
    "invalid input detected",
)


@dataclass(frozen=True)
class ProvisionCapabilities:
    domain_command: str
    domain_syntax: str
    domain_probe_output: str
    unsupported_transceiver: bool = False
    platform_punt_keepalive: bool = False
    transceiver_monitoring: bool = False

    def as_dict(self):
        return {
            "domain_command": self.domain_command,
            "domain_syntax": self.domain_syntax,
            "domain_probe_output": self.domain_probe_output,
            "unsupported_transceiver": self.unsupported_transceiver,
            "platform_punt_keepalive": self.platform_punt_keepalive,
            "transceiver_monitoring": self.transceiver_monitoring,
        }


def _command_is_supported(
    output,
):
    normalized = str(output or "").lower()

    return not any(marker in normalized for marker in INVALID_MARKERS)


def _probe_context_command(
    connection,
    command,
):
    """
    Probe de parser Cisco sem aplicar configuração real.

    Retorna True quando o parser reconhece o comando
    e False quando há Invalid/Ambiguous input.
    """
    output = connection.send_command_timing(
        command,
        strip_prompt=False,
        strip_command=False,
    )

    return (
        _command_is_supported(output),
        str(output or ""),
    )


def _probe_domain_command(
    connection,
):
    """
    Detecta a sintaxe de domain name sem alterar
    a configuração do equipamento.

    Ordem deliberada:

        ip domain name ?
        ip domain-name ?

    O '?' solicita ajuda contextual do parser IOS,
    portanto nenhum domain-name é efetivamente aplicado.
    """

    modern_output = connection.send_command_timing(
        "ip domain name",
        strip_prompt=False,
        strip_command=False,
    )

    if _command_is_supported(modern_output):
        return (
            "ip domain name",
            "ios_xe_style",
            modern_output,
        )

    classic_output = connection.send_command_timing(
        "ip domain-name",
        strip_prompt=False,
        strip_command=False,
    )

    if _command_is_supported(classic_output):
        return (
            "ip domain-name",
            "classic_style",
            classic_output,
        )

    raise RuntimeError(
        "Nenhuma sintaxe suportada para configuração "
        "de domain name foi detectada. "
        "Testadas: 'ip domain name' e "
        "'ip domain-name'."
    )


def detect_provision_capabilities(
    *,
    host,
    username,
    password,
    secret="",
    port=22,
):
    """
    Executa preflight somente-leitura/parsing.

    Não aplica configuração persistente.
    """

    connection = None

    try:
        connection = ConnectHandler(
            device_type="cisco_ios",
            host=host,
            username=username,
            password=password,
            secret=secret or "",
            port=port,
        )

        if secret:
            connection.enable()

        connection.send_command_timing(
            "configure terminal",
            strip_prompt=False,
            strip_command=False,
        )

        (
            domain_command,
            domain_syntax,
            domain_probe_output,
        ) = _probe_domain_command(connection)

        (
            unsupported_transceiver,
            _,
        ) = _probe_context_command(
            connection,
            "service unsupported-transceiver ?",
        )

        (
            platform_punt_keepalive,
            _,
        ) = _probe_context_command(
            connection,
            "platform punt-keepalive ?",
        )

        (
            transceiver_monitoring,
            _,
        ) = _probe_context_command(
            connection,
            "transceiver type ?",
        )

        return ProvisionCapabilities(
            domain_command=domain_command,
            domain_syntax=domain_syntax,
            domain_probe_output=(str(domain_probe_output or "").strip()),
            unsupported_transceiver=(unsupported_transceiver),
            platform_punt_keepalive=(platform_punt_keepalive),
            transceiver_monitoring=(transceiver_monitoring),
        )

    finally:
        if connection is not None:
            try:
                connection.send_command_timing(
                    "end",
                    strip_prompt=False,
                    strip_command=False,
                )

            except Exception:
                pass

            connection.disconnect()
