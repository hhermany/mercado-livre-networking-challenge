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

    def configure(self, hostname, vlans):
        commands = [f"hostname {hostname}"]

        for vlan_id, vlan_name in vlans:
            commands.extend([
                f"vlan {vlan_id}",
                f"name {vlan_name}",
            ])

        with ConnectHandler(**self.device) as conn:
            if self.device["secret"]:
                conn.enable()

            output = conn.send_config_set(commands)
            conn.save_config()

            validation = conn.send_command("show vlan brief")
            running_config = conn.send_command("show running-config")

        return output, validation, running_config


def save_backup(hostname, config):
    backup_dir = Path("backups")
    backup_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = backup_dir / f"{hostname}_{timestamp}.cfg"
    filename.write_text(config)

    return filename
