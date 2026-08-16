import re

from netmiko import ConnectHandler

from src.vpn.capabilities import IPsecCapabilities


class PaloAltoManager:
    def __init__(self, host, username, password):
        self.host = host
        self.username = username
        self.password = password

    def _connection_parameters(self):
        return {
            "device_type": "paloalto_panos",
            "host": self.host,
            "username": self.username,
            "password": self.password,
        }

    @staticmethod
    def _extract_named_block(text, name):
        marker = f"{name} {{"
        start = text.find(marker)

        if start < 0:
            raise ValueError(f"Crypto profile {name!r} nao encontrado no Palo Alto.")

        brace_start = text.find("{", start)
        depth = 0

        for index in range(brace_start, len(text)):
            char = text[index]

            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1

                if depth == 0:
                    return text[brace_start + 1 : index]

        raise ValueError(f"Crypto profile {name!r} possui bloco incompleto.")

    @staticmethod
    def _single_value(block, field):
        match = re.search(
            rf"\b{re.escape(field)}\s+([^\s;]+)\s*;",
            block,
        )

        if not match:
            raise ValueError(f"Campo {field!r} nao encontrado no crypto profile.")

        return match.group(1)

    @staticmethod
    def parse_ike_versions(output):
        versions = []

        if "version ikev1;" in output:
            versions.append(1)

        if "version ikev2;" in output:
            versions.append(2)

        if not versions:
            raise ValueError("Nenhuma versao IKE configurada nos gateways Palo Alto.")

        return tuple(versions)

    @classmethod
    def parse_crypto_profiles(
        cls,
        output,
        *,
        ike_profile="IKE-FGT-PA",
        ipsec_profile="IPSEC-FGT-PA",
    ):
        ike = cls._extract_named_block(
            output,
            ike_profile,
        )
        ipsec = cls._extract_named_block(
            output,
            ipsec_profile,
        )

        ike_encryption = cls._single_value(
            ike,
            "encryption",
        )
        ike_hash = cls._single_value(
            ike,
            "hash",
        )
        ike_dh = cls._single_value(
            ike,
            "dh-group",
        )

        esp = cls._extract_named_block(
            ipsec,
            "esp",
        )

        ipsec_encryption = cls._single_value(
            esp,
            "encryption",
        )
        ipsec_auth = cls._single_value(
            esp,
            "authentication",
        )
        ipsec_dh = cls._single_value(
            ipsec,
            "dh-group",
        )

        def normalize_dh(value):
            match = re.fullmatch(r"group(\d+)", value)

            if not match:
                raise ValueError(f"DH group Palo Alto invalido: {value!r}")

            return int(match.group(1))

        return IPsecCapabilities(
            ike_versions=(),
            phase1_proposals=(f"{ike_encryption}-{ike_hash}",),
            phase1_dh_groups=(normalize_dh(ike_dh),),
            phase2_proposals=(f"{ipsec_encryption}-{ipsec_auth}",),
            phase2_dh_groups=(normalize_dh(ipsec_dh),),
        )

    @staticmethod
    def _configuration_commands(
        configuration,
    ):
        commands = [line.strip() for line in configuration.splitlines() if line.strip()]

        if not commands:
            raise ValueError("Configuracao Palo Alto vazia.")

        invalid = [command for command in commands if not command.startswith("set ")]

        if invalid:
            raise ValueError("Candidate Palo Alto possui comando fora do formato set.")

        return commands

    @staticmethod
    def _assert_cli_success(
        output,
    ):
        lowered = (output or "").lower()

        errors = (
            "invalid syntax",
            "unknown command",
            "error:",
            "failed",
        )

        detected = [error for error in errors if error in lowered]

        if detected:
            raise RuntimeError(
                "Palo Alto rejeitou parte da configuracao: " + ", ".join(detected)
            )

    def apply_configuration(
        self,
        configuration,
    ):
        commands = self._configuration_commands(configuration)

        with ConnectHandler(**self._connection_parameters()) as connection:
            connection.config_mode()

            output = connection.send_config_set(
                commands,
                enter_config_mode=False,
                exit_config_mode=False,
                read_timeout=180,
            )

            self._assert_cli_success(output)

            commit_method = getattr(
                connection,
                "commit",
                None,
            )

            if callable(commit_method):
                commit_output = commit_method()
            else:
                commit_output = connection.send_command_timing(
                    "commit",
                    read_timeout=180,
                    strip_prompt=False,
                    strip_command=False,
                )

            self._assert_cli_success(commit_output)

            if connection.check_config_mode():
                connection.exit_config_mode()

        return {
            "configuration": output,
            "commit": commit_output,
        }

    def discover_ipsec_capabilities(
        self,
        *,
        ike_profile="IKE-FGT-PA",
        ipsec_profile="IPSEC-FGT-PA",
    ):
        with ConnectHandler(**self._connection_parameters()) as connection:
            connection.config_mode()

            crypto_output = connection.send_command(
                "show network ike crypto-profiles",
                read_timeout=30,
            )

            gateway_output = connection.send_command(
                "show network ike gateway",
                read_timeout=30,
            )

            connection.exit_config_mode()

        crypto_capabilities = self.parse_crypto_profiles(
            crypto_output,
            ike_profile=ike_profile,
            ipsec_profile=ipsec_profile,
        )

        return IPsecCapabilities(
            ike_versions=self.parse_ike_versions(gateway_output),
            phase1_proposals=(crypto_capabilities.phase1_proposals),
            phase1_dh_groups=(crypto_capabilities.phase1_dh_groups),
            phase2_proposals=(crypto_capabilities.phase2_proposals),
            phase2_dh_groups=(crypto_capabilities.phase2_dh_groups),
        )
