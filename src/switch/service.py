from src.switch.cisco import CiscoSwitch, save_backup


DEFAULT_VLANS = [
    (10, "VLAN_DADOS"),
    (20, "VLAN_VOZ"),
    (50, "VLAN_SEGURANCA"),
]


def provision_switch(host, username, password, hostname, secret=""):
    switch = CiscoSwitch(
        host=host,
        username=username,
        password=password,
        secret=secret,
    )

    output, vlan_state, running_config = switch.configure(
        hostname=hostname,
        vlans=DEFAULT_VLANS,
    )

    missing = []

    for vlan_id, vlan_name in DEFAULT_VLANS:
        if str(vlan_id) not in vlan_state or vlan_name not in vlan_state:
            missing.append(f"{vlan_id}:{vlan_name}")

    backup = save_backup(hostname, running_config)

    return {
        "success": not missing,
        "missing": missing,
        "backup": str(backup),
        "configuration_output": output,
        "vlan_state": vlan_state,
    }
