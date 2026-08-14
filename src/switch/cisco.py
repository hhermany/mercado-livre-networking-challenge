import re
from datetime import datetime
from pathlib import Path

from netmiko import ConnectHandler

DESCRIPTION_PATTERN = re.compile(r"^[A-Za-z0-9 _/#():-]{1,80}$")


STATUS_LABELS = {
    "connected": "Up",
    "notconnect": "Not Connected",
    "disabled": "Admin Down",
    "err-disabled": "Err-disabled",
    "inactive": "Inactive",
    "monitoring": "Monitoring",
}


INTERFACE_TYPE_ALIASES = {
    "gi": "gigabitethernet",
    "gigabitethernet": "gigabitethernet",
    "fa": "fastethernet",
    "fastethernet": "fastethernet",
    "te": "tengigabitethernet",
    "tengigabitethernet": "tengigabitethernet",
    "tengige": "tengigabitethernet",
    "eth": "ethernet",
    "ethernet": "ethernet",
    "fo": "fortygigabitethernet",
    "fortygigabitethernet": "fortygigabitethernet",
    "tw": "twentyfivegige",
    "twentyfivegige": "twentyfivegige",
    "hu": "hundredgige",
    "hundredgige": "hundredgige",
    "po": "port-channel",
    "port-channel": "port-channel",
}


def normalize_interface_name(interface):
    if not interface:
        return ""

    value = interface.strip()

    match = re.match(
        r"^([A-Za-z-]+)([0-9].*)$",
        value,
    )

    if not match:
        return value.lower()

    interface_type = match.group(1).lower()
    interface_number = match.group(2)

    normalized_type = INTERFACE_TYPE_ALIASES.get(
        interface_type,
        interface_type,
    )

    return (
        f"{normalized_type}"
        f"{interface_number}"
    ).lower()


def parse_interface_status(output):
    interfaces = []

    lines = output.splitlines()

    header = next(
        (
            line
            for line in lines
            if "Port" in line
            and "Name" in line
            and "Status" in line
            and "Vlan" in line
        ),
        None,
    )

    if header is None:
        return interfaces

    name_start = header.index("Name")
    status_start = header.index("Status")
    vlan_start = header.index("Vlan")
    duplex_start = header.index("Duplex")

    known_statuses = set(STATUS_LABELS)

    for line in lines:
        if not line.strip() or line == header:
            continue

        if len(line) < vlan_start:
            continue

        interface = line[:name_start].strip()
        description = line[name_start:status_start].strip()
        status = line[status_start:vlan_start].strip().lower()
        vlan = line[vlan_start:duplex_start].strip()

        if not interface or status not in known_statuses:
            continue

        if vlan.lower() == "routed":
            mode_label = "Routed"
        elif vlan.lower() == "trunk":
            mode_label = "Trunk"
        else:
            mode_label = f"VLAN {vlan}"

        interfaces.append(
            {
                "name": interface,
                "description": description,
                "status": status,
                "status_label": STATUS_LABELS[status],
                "vlan": vlan,
                "mode_label": mode_label,
            }
        )

    return interfaces


def parse_voice_vlans(output):
    voice_vlans = {}
    current_interface = None

    for raw_line in output.splitlines():
        line = raw_line.strip()

        if line.startswith("Name:"):
            current_interface = line.split(
                ":",
                1,
            )[1].strip()

            if current_interface:
                voice_vlans.setdefault(
                    current_interface,
                    None,
                )

            continue

        if (
            current_interface
            and line.startswith("Voice VLAN:")
        ):
            value = line.split(
                ":",
                1,
            )[1].strip()

            if value.lower() == "none":
                voice_vlans[
                    current_interface
                ] = None
                continue

            vlan_id = value.split(
                None,
                1,
            )[0]

            if vlan_id.isdigit():
                voice_vlans[
                    current_interface
                ] = int(vlan_id)

    return voice_vlans


def enrich_interfaces_with_voice_vlan(
    interfaces,
    voice_vlans,
):
    normalized_voice_vlans = {
        normalize_interface_name(name): value
        for name, value in voice_vlans.items()
    }

    enriched = []

    for item in interfaces:
        normalized_name = normalize_interface_name(
            item["name"]
        )

        voice_vlan = normalized_voice_vlans.get(
            normalized_name
        )

        enriched.append(
            {
                **item,
                "voice_vlan": voice_vlan,
                "voice_vlan_label": (
                    f"VLAN {voice_vlan}"
                    if voice_vlan is not None
                    else "--"
                ),
            }
        )

    return enriched



def parse_interface_portfast(output):
    portfast = {}
    current_interface = None

    for raw_line in output.splitlines():
        line = raw_line.strip()

        if line.startswith("interface "):
            current_interface = line.split(
                None,
                1,
            )[1].strip()

            portfast.setdefault(
                current_interface,
                None,
            )
            continue

        if current_interface is None:
            continue

        if line == "spanning-tree portfast edge":
            portfast[current_interface] = "Habilitado"

        elif line == "spanning-tree portfast":
            portfast[current_interface] = "Habilitado"

        elif line == "spanning-tree portfast network":
            portfast[current_interface] = "Network"

        elif line == "spanning-tree portfast disable":
            portfast[current_interface] = "Desabilitado"

    return portfast


def enrich_interfaces_with_portfast(
    interfaces,
    portfast,
):
    normalized_portfast = {
        normalize_interface_name(name): value
        for name, value in portfast.items()
    }

    enriched = []

    for item in interfaces:
        normalized_name = normalize_interface_name(
            item["name"]
        )

        value = normalized_portfast.get(
            normalized_name
        )

        enriched.append(
            {
                **item,
                "portfast": value,
                "portfast_label": (
                    value
                    if value is not None
                    else "--"
                ),
            }
        )

    return enriched



def parse_interface_descriptions(output):
    descriptions = {}

    for raw_line in output.splitlines():
        line = raw_line.rstrip()

        if not line.strip():
            continue

        if line.lstrip().startswith("Interface"):
            continue

        match = re.match(
            r"^(\S+)\s+"
            r"(?:admin down|up|down)\s+"
            r"(?:up|down)\s*"
            r"(.*)$",
            line,
            re.IGNORECASE,
        )

        if not match:
            continue

        interface = match.group(1).strip()
        description = match.group(2).strip()

        descriptions[
            normalize_interface_name(interface)
        ] = description

    return descriptions


def enrich_interfaces_with_descriptions(
    interfaces,
    descriptions,
):
    enriched = []

    for item in interfaces:
        normalized_name = normalize_interface_name(
            item["name"]
        )

        description = descriptions.get(
            normalized_name,
            "",
        )

        enriched.append(
            {
                **item,
                "description": description,
            }
        )

    return enriched


def validate_interface_description(description):
    if description is None:
        return

    if not DESCRIPTION_PATTERN.fullmatch(description):
        raise ValueError(
            "Descrição inválida. Use no máximo 80 caracteres e apenas "
            "letras, números, espaços e os caracteres - _ / # ( ) :"
        )


def parse_stp_capabilities(summary, running_config):
    mode_match = re.search(
        r"Switch is in (\S+) mode",
        summary,
        re.IGNORECASE,
    )

    stp_mode = (
        mode_match.group(1).lower()
        if mode_match
        else "unknown"
    )

    edge_detected = (
        "spanning-tree portfast edge"
        in running_config.lower()
    )

    return {
        "stp_mode": stp_mode,
        "portfast_supported": edge_detected,
        "portfast_mode": (
            "edge"
            if edge_detected
            else None
        ),
        "portfast_enable_command": (
            "spanning-tree portfast edge"
            if edge_detected
            else None
        ),
        "portfast_disable_command": (
            "spanning-tree portfast disable"
            if edge_detected
            else None
        ),
    }


def validate_switchport_change(
    interfaces,
    interface,
    access_vlan=None,
    voice_vlan=None,
    remove_voice_vlan=False,
    portfast_state=None,
):
    has_switchport_change = (
        access_vlan is not None
        or voice_vlan is not None
        or remove_voice_vlan
        or portfast_state is not None
    )

    if not has_switchport_change:
        return

    selected = next(
        (
            item
            for item in interfaces
            if item["name"] == interface
        ),
        None,
    )

    if selected is None:
        raise ValueError(
            f"A interface {interface} não foi encontrada no switch."
        )

    if selected["vlan"].lower() == "routed":
        raise ValueError(
            f"A interface {interface} é uma interface Layer 3 "
            "(routed). Alterações de Access/Voice VLAN ou PortFast "
            "não serão aplicadas."
        )

    if (
        portfast_state is not None
        and selected["vlan"].lower() == "trunk"
    ):
        raise ValueError(
            f"A interface {interface} está operando como trunk. "
            "PortFast Edge não será aplicado automaticamente."
        )


class CiscoSwitch:
    def __init__(self, host, username, password, secret=""):
        self.device = {
            "device_type": "cisco_ios",
            "host": host,
            "username": username,
            "password": password,
            "secret": secret,
        }

    def _connect(self):
        return ConnectHandler(**self.device)

    def list_interfaces(self):
        with self._connect() as conn:
            if self.device["secret"]:
                conn.enable()

            output = conn.send_command("show interfaces status")
            description_output = conn.send_command(
                "show interfaces description"
            )
            switchport_output = conn.send_command(
                "show interfaces switchport"
            )
            vlan_state = conn.send_command("show vlan brief")
            stp_summary = conn.send_command(
                "show spanning-tree summary"
            )
            stp_running = conn.send_command(
                "show running-config | section ^interface|spanning-tree portfast"
            )

        interfaces = parse_interface_status(
            output
        )

        descriptions = parse_interface_descriptions(
            description_output
        )

        interfaces = enrich_interfaces_with_descriptions(
            interfaces,
            descriptions,
        )

        voice_vlans = parse_voice_vlans(
            switchport_output
        )

        interfaces = enrich_interfaces_with_voice_vlan(
            interfaces,
            voice_vlans,
        )

        portfast = parse_interface_portfast(
            stp_running
        )

        interfaces = enrich_interfaces_with_portfast(
            interfaces,
            portfast,
        )

        return {
            "interfaces": interfaces,
            "raw": output,
            "vlan_state": vlan_state,
            "capabilities": parse_stp_capabilities(
                stp_summary,
                stp_running,
            ),
        }

    def list_svis(self):
        from src.switch.troubleshooting import parse_svi_interfaces

        with self._connect() as conn:
            if self.device["secret"]:
                conn.enable()

            output = conn.send_command(
                "show ip interface brief"
            )

        return {
            "svis": parse_svi_interfaces(output),
            "raw": output,
        }

    def ping(
        self,
        destination,
        source_interface,
        repeat=5,
        timeout=2,
    ):
        command = (
            f"ping {destination} "
            f"source {source_interface} "
            f"repeat {repeat} "
            f"timeout {timeout}"
        )

        with self._connect() as conn:
            if self.device["secret"]:
                conn.enable()

            output = conn.send_command(
                command,
                read_timeout=30,
            )

        return {
            "command": command,
            "output": output,
        }

    def traceroute(
        self,
        destination,
        source_ip,
    ):
        transcript = []

        with self._connect() as conn:
            if self.device["secret"]:
                conn.enable()

            output = conn.send_command_timing(
                "traceroute",
                strip_prompt=False,
                strip_command=False,
            )
            transcript.append(output)

            if "Protocol" not in output:
                raise RuntimeError(
                    "Extended Traceroute não apresentou "
                    "o prompt de protocolo."
                )

            output = conn.send_command_timing(
                "",
                strip_prompt=False,
                strip_command=False,
            )
            transcript.append(output)

            if "Target IP address" not in output:
                raise RuntimeError(
                    "Extended Traceroute não apresentou "
                    "o prompt de destino."
                )

            output = conn.send_command_timing(
                destination,
                strip_prompt=False,
                strip_command=False,
            )
            transcript.append(output)

            if "Source address" not in output:
                raise RuntimeError(
                    "Extended Traceroute não apresentou "
                    "o prompt de source."
                )

            output = conn.send_command_timing(
                source_ip,
                strip_prompt=False,
                strip_command=False,
            )
            transcript.append(output)

            default_prompts = (
                "Numeric display",
                "Timeout in seconds",
                "Probe count",
                "Minimum Time to Live",
                "Maximum Time to Live",
                "Port Number",
                "Loose, Strict, Record, Timestamp, Verbose",
            )

            for expected_prompt in default_prompts:
                if expected_prompt not in output:
                    raise RuntimeError(
                        "Extended Traceroute não apresentou "
                        f"o prompt esperado: {expected_prompt}"
                    )

                output = conn.send_command_timing(
                    "",
                    strip_prompt=False,
                    strip_command=False,
                )
                transcript.append(output)

            full_output = "".join(transcript)

            if (
                "Tracing the route" not in full_output
                and "Type escape sequence" not in full_output
            ):
                output = conn.send_command_timing(
                    "",
                    strip_prompt=False,
                    strip_command=False,
                )
                transcript.append(output)

                full_output = "".join(transcript)

        lowered = full_output.lower()

        if "% invalid input" in lowered:
            raise RuntimeError(
                "IOS rejeitou a execução do Extended Traceroute."
            )

        return {
            "mode": "extended",
            "destination": destination,
            "source_ip": source_ip,
            "output": full_output,
        }


    def configure_interfaces(
        self,
        interfaces,
        access_vlan=None,
        voice_vlan=None,
        remove_voice_vlan=False,
        description=None,
        remove_description=False,
        admin_state=None,
        portfast_state=None,
    ):
        has_switchport_config = (
            access_vlan is not None
            or voice_vlan is not None
            or remove_voice_vlan
        )

        commands = []

        for interface in interfaces:
            commands.append(
                f"interface {interface}"
            )

            if has_switchport_config:
                commands.append(
                    "switchport mode access"
                )

                if access_vlan is not None:
                    commands.append(
                        f"switchport access vlan {access_vlan}"
                    )

                if voice_vlan is not None:
                    commands.append(
                        f"switchport voice vlan {voice_vlan}"
                    )

                if remove_voice_vlan:
                    commands.append(
                        "no switchport voice vlan"
                    )

            if description is not None:
                commands.append(
                    f"description {description}"
                )

            if remove_description:
                commands.append(
                    "no description"
                )

            if admin_state == "up":
                commands.append(
                    "no shutdown"
                )

            if admin_state == "down":
                commands.append(
                    "shutdown"
                )

            if portfast_state == "enable":
                commands.append(
                    "spanning-tree portfast edge"
                )

            if portfast_state == "disable":
                commands.append(
                    "spanning-tree portfast disable"
                )

        validation = {}

        with self._connect() as conn:
            if self.device["secret"]:
                conn.enable()

            output = conn.send_config_set(
                commands
            )

            conn.save_config()

            for interface in interfaces:
                interface_outputs = []

                if has_switchport_config:
                    interface_outputs.append(
                        conn.send_command(
                            f"show interfaces {interface} switchport"
                        )
                    )

                interface_outputs.append(
                    conn.send_command(
                        f"show interfaces {interface}"
                    )
                )

                running_interface = conn.send_command(
                    f"show running-config interface {interface}"
                )

                stp_detail = ""

                if portfast_state is not None:
                    stp_detail = conn.send_command(
                        f"show spanning-tree interface "
                        f"{interface} detail"
                    )

                validation[interface] = {
                    "interface_state": "\n\n".join(
                        interface_outputs
                    ),
                    "running_config": running_interface,
                    "stp_detail": stp_detail,
                }

            running_config = conn.send_command(
                "show running-config"
            )

        return (
            output,
            validation,
            running_config,
        )

    def configure(
        self,
        hostname=None,
        vlans=None,
        interface=None,
        access_vlan=None,
        voice_vlan=None,
        remove_voice_vlan=False,
        description=None,
        remove_description=False,
        admin_state=None,
    ):
        vlans = vlans or []

        vlan_commands = []

        for vlan_id, vlan_name in vlans:
            vlan_commands.extend(
                [
                    f"vlan {vlan_id}",
                    f"name {vlan_name}",
                ]
            )

        interface_commands = []

        has_switchport_config = (
            access_vlan is not None
            or voice_vlan is not None
            or remove_voice_vlan
        )

        if interface and has_switchport_config:
            interface_commands.extend(
                [
                    f"interface {interface}",
                    "switchport mode access",
                ]
            )

            if access_vlan is not None:
                interface_commands.append(
                    f"switchport access vlan {access_vlan}"
                )

            if voice_vlan is not None:
                interface_commands.append(
                    f"switchport voice vlan {voice_vlan}"
                )

            if remove_voice_vlan:
                interface_commands.append(
                    "no switchport voice vlan"
                )

        if interface and (description is not None or remove_description):
            if not interface_commands:
                interface_commands.append(
                    f"interface {interface}"
                )

            if description is not None:
                interface_commands.append(
                    f"description {description}"
                )

            if remove_description:
                interface_commands.append(
                    "no description"
                )

        if interface and admin_state:
            if not interface_commands:
                interface_commands.append(
                    f"interface {interface}"
                )

            if admin_state == "up":
                interface_commands.append("no shutdown")
            elif admin_state == "down":
                interface_commands.append("shutdown")
            else:
                raise ValueError(
                    "admin_state deve ser 'up' ou 'down'."
                )

        outputs = []

        with self._connect() as conn:
            if self.device["secret"]:
                conn.enable()

            if hostname:
                hostname_output = conn.send_config_set(
                    [f"hostname {hostname}"],
                    cmd_verify=False,
                )
                outputs.append(hostname_output)
                conn.set_base_prompt()

            if vlan_commands:
                vlan_output = conn.send_config_set(vlan_commands)
                outputs.append(vlan_output)

            if interface_commands:
                interface_output = conn.send_config_set(
                    interface_commands
                )
                outputs.append(interface_output)

            conn.save_config()

            vlan_state = conn.send_command("show vlan brief")
            interface_state = ""

            if interface:
                interface_outputs = []

                if has_switchport_config:
                    interface_outputs.append(
                        conn.send_command(
                            f"show interfaces {interface} switchport"
                        )
                    )

                interface_outputs.append(
                    conn.send_command(
                        f"show interfaces {interface}"
                    )
                )

                interface_state = "\n\n".join(interface_outputs)

            running_config = conn.send_command(
                "show running-config"
            )

        return (
            "\n".join(outputs),
            vlan_state,
            interface_state,
            running_config,
        )


def save_backup(hostname, config):
    backup_dir = Path("backups")
    backup_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_name = hostname or "SWITCH"
    filename = backup_dir / f"{backup_name}_{timestamp}.cfg"
    filename.write_text(config)

    return filename
