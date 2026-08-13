from src.switch.cisco import CiscoSwitch, save_backup


def provision_switch(
    host,
    username,
    password,
    hostname=None,
    secret="",
    vlans=None,
):
    desired_vlans = vlans or []

    if not hostname and not desired_vlans:
        raise ValueError(
            "Informe um hostname ou pelo menos uma VLAN para configurar."
        )

    switch = CiscoSwitch(
        host=host,
        username=username,
        password=password,
        secret=secret,
    )

    output, vlan_state, running_config = switch.configure(
        hostname=hostname,
        vlans=desired_vlans,
    )

    missing = []

    if hostname:
        expected_hostname = f"hostname {hostname}"

        if expected_hostname not in running_config:
            missing.append(f"hostname:{hostname}")

    for vlan_id, vlan_name in desired_vlans:
        vlan_id = str(vlan_id)

        matching_lines = [
            line
            for line in vlan_state.splitlines()
            if line.strip().startswith(f"{vlan_id} ")
        ]

        if not matching_lines or vlan_name not in matching_lines[0]:
            missing.append(f"vlan:{vlan_id}:{vlan_name}")

    backup = save_backup(hostname, running_config)

    return {
        "success": not missing,
        "missing": missing,
        "backup": str(backup),
        "configuration_output": output,
        "vlan_state": vlan_state,
        "hostname": hostname,
    }
