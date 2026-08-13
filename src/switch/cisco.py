from datetime import datetime
from pathlib import Path

from netmiko import ConnectHandler


class CiscoSwitch:
    def __init__(self, host, username, password, secret=""):
        self.device = {
            "device_type": "cisco_ios",
            "host": host,
            "username": username,
            "password": password,
            "secret": secret,
        }

    def configure(
        self,
        hostname=None,
        vlans=None,
        interface=None,
        access_vlan=None,
        voice_vlan=None,
    ):
        vlans = vlans or []

        vlan_commands = []

        for vlan_id, vlan_name in vlans:
            vlan_commands.extend([
                f"vlan {vlan_id}",
                f"name {vlan_name}",
            ])

        interface_commands = []

        if interface:
            interface_commands.extend([
                f"interface {interface}",
                "switchport mode access",
            ])

            if access_vlan is not None:
                interface_commands.append(
                    f"switchport access vlan {access_vlan}"
                )

            if voice_vlan is not None:
                interface_commands.append(
                    f"switchport voice vlan {voice_vlan}"
                )

        outputs = []

        with ConnectHandler(**self.device) as conn:
            if self.device["secret"]:
                conn.enable()

            if hostname:
                hostname_output = conn.send_config_set(
                    [f"hostname {hostname}"],
                    cmd_verify=False,
                )
                outputs.append(hostname_output)

                # O prompt muda após o comando hostname.
                conn.set_base_prompt()

            if vlan_commands:
                vlan_output = conn.send_config_set(vlan_commands)
                outputs.append(vlan_output)

            if interface_commands:
                interface_output = conn.send_config_set(interface_commands)
                outputs.append(interface_output)

            conn.save_config()

            vlan_state = conn.send_command("show vlan brief")

            interface_state = ""

            if interface:
                interface_state = conn.send_command(
                    f"show interfaces {interface} switchport"
                )

            running_config = conn.send_command("show running-config")

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
