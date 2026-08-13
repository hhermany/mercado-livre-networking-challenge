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

    def configure(self, hostname=None, vlans=None):
        vlans = vlans or []

        vlan_commands = []

        for vlan_id, vlan_name in vlans:
            vlan_commands.extend([
                f"vlan {vlan_id}",
                f"name {vlan_name}",
            ])

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

            conn.save_config()

            validation = conn.send_command("show vlan brief")
            running_config = conn.send_command("show running-config")

        return "\n".join(outputs), validation, running_config


def save_backup(hostname, config):
    backup_dir = Path("backups")
    backup_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_name = hostname or "SWITCH"
    filename = backup_dir / f"{backup_name}_{timestamp}.cfg"
    filename.write_text(config)

    return filename
