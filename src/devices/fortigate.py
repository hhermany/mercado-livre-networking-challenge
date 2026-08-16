import re
import time

from netmiko import ConnectHandler

from src.devices.base import DeviceDriver
from src.vpn.capabilities import IPsecCapabilities


class FortiGateDriver(DeviceDriver):
    """FortiGate device driver."""

    def __init__(
        self,
        *,
        host,
        username,
        password,
        port=22,
    ):
        self.host = host
        self.username = username
        self.password = password
        self.port = port

    def _connection_parameters(self):
        return {
            "device_type": "fortinet",
            "host": self.host,
            "username": self.username,
            "password": self.password,
            "port": self.port,
        }

    def discover(self):
        with ConnectHandler(**self._connection_parameters()) as connection:
            output = connection.send_command("get system status")

        hostname = None
        version = None
        serial = None

        for raw_line in output.splitlines():
            line = raw_line.strip()

            if line.startswith("Hostname:"):
                hostname = line.split(
                    ":",
                    1,
                )[1].strip()

            elif line.startswith("Version:"):
                version = line.split(
                    ":",
                    1,
                )[1].strip()

            elif line.startswith("Serial-Number:"):
                serial = line.split(
                    ":",
                    1,
                )[1].strip()

        return {
            "hostname": hostname or self.host,
            "version": version,
            "serial": serial,
        }

    @staticmethod
    def _parse_cli_choices(
        output,
        *,
        numeric=False,
    ):
        values = []

        ignored = {
            "command",
            "parse",
            "error",
            "unknown",
            "return",
            "incomplete",
        }

        for raw_line in output.splitlines():
            line = raw_line.strip()

            if not line:
                continue

            if line.startswith(
                (
                    "#",
                    "(",
                    "FW-",
                    "config ",
                    "edit ",
                    "set ",
                )
            ):
                continue

            token = line.split()[0].strip()

            if not token:
                continue

            if token.lower() in ignored:
                continue

            if numeric:
                try:
                    value = int(token)
                except ValueError:
                    continue

                if value not in values:
                    values.append(value)

            else:
                if token not in values:
                    values.append(token)

        return tuple(values)

    def discover_ipsec_capabilities(
        self,
        *,
        phase1_name="VPN1-PA-DC",
        phase2_name="VPN1-PA-DC-P2",
    ):
        """
        Consulta o CLI do FortiGate sem alterar configuracao.

        Usa objetos IPsec existentes apenas como contexto
        para obter as opcoes aceitas pelo FortiOS.
        """

        with ConnectHandler(**self._connection_parameters()) as connection:

            def command(value):
                return connection.send_command_timing(
                    value,
                    strip_prompt=False,
                    strip_command=False,
                )

            command("config vpn ipsec phase1-interface")
            command(f'edit "{phase1_name}"')

            phase1_proposals = self._parse_cli_choices(command("set proposal ?"))

            phase1_dh = self._parse_cli_choices(
                command("set dhgrp ?"),
                numeric=True,
            )

            ike_versions = self._parse_cli_choices(
                command("set ike-version ?"),
                numeric=True,
            )

            command("end")

            command("config vpn ipsec phase2-interface")
            command(f'edit "{phase2_name}"')

            phase2_proposals = self._parse_cli_choices(command("set proposal ?"))

            phase2_dh = self._parse_cli_choices(
                command("set dhgrp ?"),
                numeric=True,
            )

            command("end")

        if not phase1_proposals:
            raise RuntimeError("FortiGate nao retornou proposals de Phase1.")

        if not phase2_proposals:
            raise RuntimeError("FortiGate nao retornou proposals de Phase2.")

        if not phase1_dh:
            raise RuntimeError("FortiGate nao retornou DH Groups de Phase1.")

        if not phase2_dh:
            raise RuntimeError("FortiGate nao retornou DH Groups de Phase2.")

        if not ike_versions:
            raise RuntimeError("FortiGate nao retornou IKE versions.")

        return IPsecCapabilities(
            ike_versions=ike_versions,
            phase1_proposals=phase1_proposals,
            phase1_dh_groups=phase1_dh,
            phase2_proposals=phase2_proposals,
            phase2_dh_groups=phase2_dh,
        )

    @staticmethod
    def _configuration_commands(
        configuration,
    ):
        return [line.rstrip() for line in configuration.splitlines() if line.strip()]

    @staticmethod
    def _cli_warnings(
        output,
    ):
        """
        Extrai mensagens de erro/warning retornadas pelo FortiOS.

        O FortiGate pode retornar Command fail / Return code
        para comandos idempotentes ou atributos que ja estejam
        no estado desejado, mesmo quando o Candidate final fica
        corretamente aplicado.

        Portanto estas mensagens nao determinam sozinhas o
        resultado do Deploy. O estado final e validado depois.
        """
        error_markers = (
            "command fail",
            "parse error",
            "unknown action",
            "return code -",
            "invalid command",
        )

        lines = []

        for line in str(output or "").splitlines():
            lowered = line.lower()

            if any(marker in lowered for marker in error_markers):
                value = line.strip()

                if value and value not in lines:
                    lines.append(value)

        return tuple(lines)

    @classmethod
    def _assert_cli_success(
        cls,
        output,
    ):
        """
        Compatibilidade com callers/testes antigos.

        Erros CLI sao tratados como warnings nesta etapa.
        A decisao final ocorre em validate_configuration().
        """
        return cls._cli_warnings(output)

    def apply_configuration(
        self,
        configuration: str,
    ) -> str:
        commands = self._configuration_commands(configuration)

        if not commands:
            raise ValueError("Configuracao FortiGate vazia.")

        with ConnectHandler(**self._connection_parameters()) as connection:
            output = connection.send_config_set(
                commands,
                enter_config_mode=False,
                exit_config_mode=False,
                read_timeout=180,
            )

        # O output bruto pode conter warnings do FortiOS.
        # Nao transformamos isso automaticamente em falha:
        # o estado final sera validado apos a aplicacao.
        self._assert_cli_success(output)

        return output

    def validate_configuration(
        self,
        *,
        expected_hostname=None,
    ) -> bool:
        """
        Valida o estado efetivamente aplicado.

        Para uma Branch provisionada:
        - hostname deve corresponder ao Candidate;
        - VPN1 e VPN2 devem existir;
        - Phase2 deve existir;
        - BGP deve possuir dois neighbors;
        - SD-WAN deve possuir VPN1/VPN2.

        A validacao e de configuracao, nao depende das VPNs
        ja estarem operacionais no mesmo segundo do Deploy.
        """

        with ConnectHandler(**self._connection_parameters()) as connection:
            global_config = connection.send_command(
                "show system global",
                read_timeout=30,
            )

            interfaces = connection.send_command(
                "show system interface",
                read_timeout=30,
            )

            phase1 = connection.send_command(
                "show vpn ipsec phase1-interface",
                read_timeout=30,
            )

            phase2 = connection.send_command(
                "show vpn ipsec phase2-interface",
                read_timeout=30,
            )

            bgp = connection.send_command(
                "show router bgp",
                read_timeout=30,
            )

            sdwan = connection.send_command(
                "show system sdwan",
                read_timeout=30,
            )

        if expected_hostname:
            hostname_marker = f'set hostname "{expected_hostname}"'

            if hostname_marker not in global_config:
                raise RuntimeError(
                    "Hostname apos Deploy nao "
                    "corresponde ao Candidate: "
                    f"{expected_hostname}"
                )

        required = {
            "VPN1 system interface": (
                interfaces,
                'edit "VPN1-PA-DC"',
            ),
            "VPN2 system interface": (
                interfaces,
                'edit "VPN2-PA-DC"',
            ),
            "VPN1 Phase1": (
                phase1,
                'edit "VPN1-PA-DC"',
            ),
            "VPN2 Phase1": (
                phase1,
                'edit "VPN2-PA-DC"',
            ),
            "VPN1 Phase2": (
                phase2,
                'edit "VPN1-PA-DC-P2"',
            ),
            "VPN2 Phase2": (
                phase2,
                'edit "VPN2-PA-DC-P2"',
            ),
            "SD-WAN VPN1": (
                sdwan,
                'set interface "VPN1-PA-DC"',
            ),
            "SD-WAN VPN2": (
                sdwan,
                'set interface "VPN2-PA-DC"',
            ),
        }

        missing = [
            name
            for name, (
                output,
                marker,
            ) in required.items()
            if marker not in output
        ]

        neighbor_count = bgp.count("set remote-as 65001")

        if neighbor_count < 2:
            missing.append("BGP dois neighbors")

        if missing:
            raise RuntimeError(
                "Post-validation FortiGate falhou: " + ", ".join(missing)
            )

        return True

    def validate_operational_state(
        self,
        *,
        expected_lan_gateway,
        expected_loopback_ip,
        expected_vpn1_fg_ip,
        expected_vpn2_fg_ip,
        expected_bgp_neighbors,
        expected_dhcp_start,
        expected_dhcp_end,
        expected_vpn_names=(
            "VPN1-PA-DC",
            "VPN2-PA-DC",
        ),
        expected_dc_prefix="10.255.255.0/24",
        attempts=12,
        interval=5,
    ):
        """
        Valida convergencia operacional apos o Deploy.

        Diferente de validate_configuration(), esta rotina
        exige VPN, BGP e SD-WAN efetivamente operacionais.

        Retry existe porque IKE/BGP podem levar alguns
        segundos para convergir depois da configuracao.
        """

        if attempts < 1:
            raise ValueError("attempts deve ser >= 1.")

        vpn1_peer, vpn2_peer = expected_bgp_neighbors
        vpn1_name, vpn2_name = expected_vpn_names

        last_missing = []

        with ConnectHandler(**self._connection_parameters()) as connection:
            for attempt in range(
                1,
                attempts + 1,
            ):
                interfaces = connection.send_command(
                    "show system interface",
                    read_timeout=30,
                )

                dhcp = connection.send_command(
                    "show system dhcp server",
                    read_timeout=30,
                )

                vpn = connection.send_command(
                    "get vpn ipsec tunnel summary",
                    read_timeout=30,
                )

                bgp = connection.send_command(
                    "get router info bgp summary",
                    read_timeout=30,
                )

                routes = connection.send_command(
                    "get router info routing-table all",
                    read_timeout=30,
                )

                sdwan = connection.send_command(
                    "diagnose sys sdwan health-check",
                    read_timeout=30,
                )

                missing = []

                interface_checks = (
                    (
                        "LAN gateway",
                        (f"set ip {expected_lan_gateway} 255.255.255.0"),
                    ),
                    (
                        "LO-MGMT",
                        (f"set ip {expected_loopback_ip} 255.255.255.255"),
                    ),
                    (
                        "VPN1 overlay IP",
                        (f"set ip {expected_vpn1_fg_ip} 255.255.255.255"),
                    ),
                    (
                        "VPN2 overlay IP",
                        (f"set ip {expected_vpn2_fg_ip} 255.255.255.255"),
                    ),
                )

                for name, marker_value in interface_checks:
                    if marker_value not in interfaces:
                        missing.append(name)

                dhcp_checks = (
                    (
                        "DHCP interface port4",
                        'set interface "port4"',
                    ),
                    (
                        "DHCP gateway",
                        (f"set default-gateway {expected_lan_gateway}"),
                    ),
                    (
                        "DHCP start",
                        (f"set start-ip {expected_dhcp_start}"),
                    ),
                    (
                        "DHCP end",
                        (f"set end-ip {expected_dhcp_end}"),
                    ),
                    (
                        "DHCP DNS",
                        "set dns-server1 10.255.255.1",
                    ),
                )

                for name, marker_value in dhcp_checks:
                    if marker_value not in dhcp:
                        missing.append(name)

                vpn_checks = (
                    (
                        "VPN1 IPsec UP",
                        vpn1_name,
                    ),
                    (
                        "VPN2 IPsec UP",
                        vpn2_name,
                    ),
                )

                for name, vpn_name in vpn_checks:
                    pattern = (
                        rf"'{re.escape(vpn_name)}'"
                        r".*selectors\(total,up\):"
                        r"\s*1/1"
                    )

                    if not re.search(
                        pattern,
                        vpn,
                    ):
                        missing.append(name)

                for peer_name, peer_ip in (
                    (
                        "BGP VPN1 Established",
                        vpn1_peer,
                    ),
                    (
                        "BGP VPN2 Established",
                        vpn2_peer,
                    ),
                ):
                    peer_line = None

                    for line in bgp.splitlines():
                        if line.strip().startswith(peer_ip):
                            peer_line = line
                            break

                    if peer_line is None:
                        missing.append(peer_name)
                        continue

                    # FortiGate mostra PfxRcd numerico
                    # quando o neighbor esta Established.
                    if not re.search(
                        r"\s+\d+\s*$",
                        peer_line,
                    ):
                        missing.append(peer_name)

                if expected_dc_prefix not in routes:
                    missing.append("Rota DC via BGP")

                if vpn1_name not in routes or vpn2_name not in routes:
                    missing.append("ECMP DC VPN1/VPN2")

                sdwan_checks = (
                    (
                        "SD-WAN VPN1 alive",
                        (f"Seq(1 {vpn1_name}): state(alive)"),
                    ),
                    (
                        "SD-WAN VPN2 alive",
                        (f"Seq(2 {vpn2_name}): state(alive)"),
                    ),
                )

                for name, marker_value in sdwan_checks:
                    if marker_value not in sdwan:
                        missing.append(name)

                if not missing:
                    return True

                last_missing = missing

                if attempt < attempts:
                    time.sleep(interval)

        raise RuntimeError(
            "Post-validation operacional FortiGate falhou: " + ", ".join(last_missing)
        )


def discover_managed_fortigate(device):
    driver = FortiGateDriver(**device.credentials())

    return driver.discover()
