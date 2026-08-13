from src.switch.cisco import CiscoSwitch, save_backup


def provision_switch(
    host,
    username,
    password,
    hostname=None,
    secret="",
    vlans=None,
    interface=None,
    access_vlan=None,
    voice_vlan=None,
):
    desired_vlans = vlans or []

    has_interface_config = (
        access_vlan is not None or voice_vlan is not None
    )

    if has_interface_config and not interface:
        raise ValueError(
            "Informe a interface para configurar Access VLAN ou Voice VLAN."
        )

    if not hostname and not desired_vlans and not has_interface_config:
        raise ValueError(
            "Informe um hostname, pelo menos uma VLAN "
            "ou uma configuração de interface."
        )

    switch = CiscoSwitch(
        host=host,
        username=username,
        password=password,
        secret=secret,
    )

    output, vlan_state, interface_state, running_config = switch.configure(
        hostname=hostname,
        vlans=desired_vlans,
        interface=interface,
        access_vlan=access_vlan,
        voice_vlan=voice_vlan,
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

    if has_interface_config:
        if "Administrative Mode: static access" not in interface_state:
            missing.append(f"interface:{interface}:mode-access")

        if access_vlan is not None:
            access_marker = f"Access Mode VLAN: {access_vlan}"

            if access_marker not in interface_state:
                missing.append(
                    f"interface:{interface}:access-vlan:{access_vlan}"
                )

        if voice_vlan is not None:
            voice_marker = f"Voice VLAN: {voice_vlan}"

            if voice_marker not in interface_state:
                missing.append(
                    f"interface:{interface}:voice-vlan:{voice_vlan}"
                )

    backup = save_backup(hostname, running_config)

    return {
        "success": not missing,
        "missing": missing,
        "backup": str(backup),
        "configuration_output": output,
        "vlan_state": vlan_state,
        "interface_state": interface_state,
        "hostname": hostname,
    }
