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


def validate_interface_description(description):
    if description is None:
        return

    if not DESCRIPTION_PATTERN.fullmatch(description):
        raise ValueError(
            "Descrição inválida. Use no máximo 80 caracteres e apenas "
            "letras, números, espaços e os caracteres - _ / # ( ) :"
        )


def validate_switchport_change(
    interfaces,
    interface,
    access_vlan=None,
    voice_vlan=None,
    remove_voice_vlan=False,
):
    has_switchport_change = (
        access_vlan is not None
        or voice_vlan is not None
        or remove_voice_vlan
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
            "(routed). Alterações de Access/Voice VLAN não serão aplicadas."
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
            vlan_state = conn.send_command("show vlan brief")

        return {
            "interfaces": parse_interface_status(output),
            "raw": output,
            "vlan_state": vlan_state,
        }

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
