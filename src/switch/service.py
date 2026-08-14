import re

from src.switch.cisco import (
    CiscoSwitch,
    save_backup,
    validate_interface_description,
)


def get_switch_interfaces(
    host,
    username,
    password,
    secret="",
):
    switch = CiscoSwitch(
        host=host,
        username=username,
        password=password,
        secret=secret,
    )

    return switch.list_interfaces()


def _interface_counter(interface_state, counter_name):
    pattern = (
        rf"(?<![A-Za-z0-9_])"
        rf"(\d+)\s+{re.escape(counter_name)}\b"
    )

    match = re.search(
        pattern,
        interface_state,
        re.IGNORECASE,
    )

    if not match:
        return 0

    return int(match.group(1))


def _nonzero_counters(interface_state, counter_names):
    counters = {}

    for counter_name in counter_names:
        value = _interface_counter(
            interface_state,
            counter_name,
        )

        if value > 0:
            counters[counter_name] = value

    return counters


def _format_counters(counters):
    return ", ".join(
        f"{name}: {value}"
        for name, value in counters.items()
    )


def highlight_interface_counters(summary):
    if not summary:
        return ""

    counter_classes = {
        "lost carrier": "danger",
        "no carrier": "danger",
        "CRC": "warning",
        "frame": "warning",
        "runts": "warning",
        "giants": "warning",
        "late collision": "warning",
        "collisions": "warning",
        "overrun": "warning",
        "ignored": "warning",
        "throttles": "warning",
        "output errors": "warning",
        "underruns": "warning",
        "output buffer failures": "warning",
        "input errors": "warning",
    }

    highlighted = summary

    for counter_name, level in counter_classes.items():
        pattern = re.compile(
            rf"(?<!\d)([1-9]\d*)\s+"
            rf"({re.escape(counter_name)})(?![A-Za-z])",
            re.IGNORECASE,
        )

        css_class = (
            "counter-highlight "
            f"counter-highlight-{level}"
        )

        highlighted = pattern.sub(
            lambda match, css_class=css_class: (
                f'<span class="{css_class}">'
                f"{match.group(1)} {match.group(2)}"
                "</span>"
            ),
            highlighted,
        )

    return highlighted


def classify_interface_health(interface_state):
    if not interface_state:
        return {
            "level": "neutral",
            "label": "Sem dados operacionais",
            "issues": [],
        }

    issues = []

    # Cisco: lost carrier / no carrier direcionam primeiro
    # para cabo e conexão física nas duas extremidades.
    carrier_counters = _nonzero_counters(
        interface_state,
        (
            "lost carrier",
            "no carrier",
        ),
    )

    if carrier_counters:
        issues.append(
            {
                "level": "danger",
                "category": "physical",
                "title": (
                    "Possível problema físico ou de cabeamento"
                ),
                "detail": (
                    f"{_format_counters(carrier_counters)}. "
                    "Foi detectada perda de carrier. "
                    "Verifique o cabo, conectores, a porta física "
                    "e a conexão no equipamento remoto."
                ),
            }
        )

    # Cisco: CRC/frame/runts podem ser problema físico,
    # NIC/porta, ruído ou incompatibilidade de duplex.
    physical_duplex_counters = _nonzero_counters(
        interface_state,
        (
            "CRC",
            "frame",
            "runts",
        ),
    )

    if physical_duplex_counters:
        issues.append(
            {
                "level": "warning",
                "category": "physical-duplex",
                "title": (
                    "Indício de problema físico ou de duplex"
                ),
                "detail": (
                    f"{_format_counters(physical_duplex_counters)}. "
                    "Avalie cabeamento, porta/NIC, ruído "
                    "e negociação de speed/duplex."
                ),
            }
        )

    # Giants são tratados separadamente porque a documentação
    # Cisco aponta principalmente para o dispositivo/NIC remoto.
    giant_counters = _nonzero_counters(
        interface_state,
        (
            "giants",
        ),
    )

    if giant_counters:
        issues.append(
            {
                "level": "warning",
                "category": "endpoint",
                "title": (
                    "Frames inválidos de tamanho excessivo"
                ),
                "detail": (
                    f"{_format_counters(giant_counters)}. "
                    "Avalie principalmente o dispositivo/NIC "
                    "conectado e a configuração da interface."
                ),
            }
        )

    late_collision_counters = _nonzero_counters(
        interface_state,
        (
            "late collision",
        ),
    )

    if late_collision_counters:
        issues.append(
            {
                "level": "warning",
                "category": "duplex",
                "title": (
                    "Possível problema de duplex ou meio físico"
                ),
                "detail": (
                    f"{_format_counters(late_collision_counters)}. "
                    "Verifique speed/duplex e o segmento físico."
                ),
            }
        )

    collisions = _nonzero_counters(
        interface_state,
        (
            "collisions",
        ),
    )

    full_duplex = bool(
        re.search(
            r"\bfull[- ]duplex\b",
            interface_state,
            re.IGNORECASE,
        )
    )

    if collisions and full_duplex:
        issues.append(
            {
                "level": "warning",
                "category": "duplex",
                "title": (
                    "Colisões detectadas em full-duplex"
                ),
                "detail": (
                    f"{_format_counters(collisions)}. "
                    "Colisões não são esperadas em uma "
                    "interface operando em full-duplex; "
                    "verifique a negociação com o equipamento remoto."
                ),
            }
        )

    # Problemas de recepção/capacidade.
    receive_resource_counters = _nonzero_counters(
        interface_state,
        (
            "overrun",
            "ignored",
            "throttles",
        ),
    )

    if receive_resource_counters:
        issues.append(
            {
                "level": "warning",
                "category": "resources",
                "title": (
                    "Atenção a capacidade de recepção"
                ),
                "detail": (
                    f"{_format_counters(receive_resource_counters)}. "
                    "Os contadores indicam pressão de buffers, "
                    "rajadas ou excesso de tráfego/processamento."
                ),
            }
        )

    # Problemas de saída/buffer/congestionamento.
    transmit_resource_counters = _nonzero_counters(
        interface_state,
        (
            "output errors",
            "underruns",
            "output buffer failures",
        ),
    )

    if transmit_resource_counters:
        issues.append(
            {
                "level": "warning",
                "category": "congestion",
                "title": (
                    "Possível congestionamento ou pressão de buffers"
                ),
                "detail": (
                    f"{_format_counters(transmit_resource_counters)}. "
                    "Avalie utilização, velocidade da interface "
                    "e capacidade das filas/buffers."
                ),
            }
        )

    # Input errors é agregado. Só gera mensagem própria quando
    # existe erro de entrada sem um dos contadores específicos
    # que já explicamos acima.
    input_errors = _interface_counter(
        interface_state,
        "input errors",
    )

    specific_input = {
        **physical_duplex_counters,
        **giant_counters,
        **receive_resource_counters,
    }

    if input_errors > 0 and not specific_input:
        issues.append(
            {
                "level": "warning",
                "category": "input",
                "title": "Erros de entrada detectados",
                "detail": (
                    f"input errors: {input_errors}. "
                    "O contador é agregado; investigue os "
                    "contadores detalhados e o comportamento "
                    "da interface."
                ),
            }
        )

    admin_down = (
        "administratively down"
        in interface_state.lower()
    )

    operational_up = bool(
        re.search(
            r"\bis up,\s+line protocol is up\b",
            interface_state,
            re.IGNORECASE,
        )
    )

    if any(
        issue["level"] == "danger"
        for issue in issues
    ):
        level = "danger"
        label = "Alerta físico/cabeamento"

    elif issues:
        level = "warning"
        label = "Atenção necessária"

    elif admin_down:
        level = "neutral"
        label = "Administrativamente desativada"

    elif operational_up:
        level = "healthy"
        label = "Porta funcional"

    else:
        level = "neutral"
        label = "Link indisponível"

    return {
        "level": level,
        "label": label,
        "issues": issues,
    }


def summarize_interface_state(interface_state):
    if not interface_state:
        return ""

    prefixes = (
        "Switchport:",
        "Administrative Mode:",
        "Operational Mode:",
        "Access Mode VLAN:",
        "Administrative Native VLAN tagging:",
        "Voice VLAN:",
    )

    contains = (
        " line protocol is ",
        "MTU ",
        " runts,",
        " input errors,",
        " packets output,",
        " output errors,",
        " unknown protocol drops",
        " babbles,",
        " lost carrier,",
        " output buffer failures,",
    )

    selected = []

    for line in interface_state.splitlines():
        stripped = line.strip()

        if not stripped:
            continue

        if stripped.startswith(prefixes):
            selected.append(line.rstrip())
            continue

        if any(marker in line for marker in contains):
            selected.append(line.rstrip())

    return "\n".join(selected)


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
    remove_voice_vlan=False,
    description=None,
    remove_description=False,
    admin_state=None,
):
    desired_vlans = vlans or []

    validate_interface_description(description)

    if description is not None and remove_description:
        raise ValueError(
            "Informe uma descrição ou escolha remover a descrição, "
            "não as duas opções ao mesmo tempo."
        )

    if voice_vlan is not None and remove_voice_vlan:
        raise ValueError(
            "Informe uma Voice VLAN ou escolha remover a Voice VLAN, "
            "não as duas opções ao mesmo tempo."
        )

    has_interface_config = (
        access_vlan is not None
        or voice_vlan is not None
        or remove_voice_vlan
        or description is not None
        or remove_description
        or admin_state is not None
    )

    if has_interface_config and not interface:
        raise ValueError(
            "Informe a interface para configurar Access VLAN, Voice VLAN, "
            "descrição ou estado administrativo."
        )

    if admin_state not in (None, "up", "down"):
        raise ValueError(
            "Estado administrativo deve ser 'up' ou 'down'."
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
        remove_voice_vlan=remove_voice_vlan,
        description=description,
        remove_description=remove_description,
        admin_state=admin_state,
    )

    missing = []
    changes = []

    if hostname:
        expected_hostname = f"hostname {hostname}"

        if expected_hostname not in running_config:
            missing.append(f"hostname:{hostname}")

        changes.append(f"Hostname: {hostname}")

    for vlan_id, vlan_name in desired_vlans:
        vlan_id = str(vlan_id)

        matching_lines = [
            line
            for line in vlan_state.splitlines()
            if line.strip().startswith(f"{vlan_id} ")
        ]

        if not matching_lines or vlan_name not in matching_lines[0]:
            missing.append(f"vlan:{vlan_id}:{vlan_name}")

        changes.append(
            f"VLAN {vlan_id}: {vlan_name}"
        )

    has_switchport_config = (
        access_vlan is not None
        or voice_vlan is not None
        or remove_voice_vlan
    )

    if has_switchport_config:
        if "Administrative Mode: static access" not in interface_state:
            missing.append(
                f"interface:{interface}:mode-access"
            )

        if access_vlan is not None:
            access_marker = f"Access Mode VLAN: {access_vlan}"

            if access_marker not in interface_state:
                missing.append(
                    f"interface:{interface}:access-vlan:{access_vlan}"
                )

            changes.append(
                f"{interface}: Access VLAN {access_vlan}"
            )

        if voice_vlan is not None:
            voice_marker = f"Voice VLAN: {voice_vlan}"

            if voice_marker not in interface_state:
                missing.append(
                    f"interface:{interface}:voice-vlan:{voice_vlan}"
                )

            changes.append(
                f"{interface}: Voice VLAN {voice_vlan}"
            )

        if remove_voice_vlan:
            if "Voice VLAN: none" not in interface_state:
                missing.append(
                    f"interface:{interface}:remove-voice-vlan"
                )

            changes.append(
                f"{interface}: Voice VLAN removida"
            )

    if description is not None:
        expected_description = f"description {description}"

        interface_config_lines = [
            line.strip()
            for line in running_config.splitlines()
        ]

        if expected_description not in interface_config_lines:
            missing.append(
                f"interface:{interface}:description"
            )

        changes.append(
            f"{interface}: Description alterada para {description}"
        )

    if remove_description:
        interface_config_lines = [
            line.strip()
            for line in running_config.splitlines()
        ]

        if any(
            line.startswith("description ")
            for line in interface_config_lines
        ):
            missing.append(
                f"interface:{interface}:remove-description"
            )

        changes.append(
            f"{interface}: Description removida"
        )

    if admin_state == "down":
        if "administratively down" not in interface_state.lower():
            missing.append(
                f"interface:{interface}:admin-down"
            )

        changes.append(
            f"{interface}: Admin Down"
        )

    if admin_state == "up":
        if "administratively down" in interface_state.lower():
            missing.append(
                f"interface:{interface}:admin-up"
            )

        changes.append(
            f"{interface}: Admin Up"
        )

    backup = save_backup(hostname, running_config)

    return {
        "success": not missing,
        "missing": missing,
        "changes": changes,
        "backup": str(backup),
        "configuration_output": output,
        "vlan_state": vlan_state,
        "interface_state": interface_state,
        "interface_summary": summarize_interface_state(
            interface_state
        ),
        "hostname": hostname,
    }


def provision_interfaces_batch(
    host,
    username,
    password,
    interfaces,
    secret="",
    access_vlan=None,
    voice_vlan=None,
    remove_voice_vlan=False,
    description=None,
    remove_description=False,
    admin_state=None,
    portfast_state=None,
):
    interfaces = interfaces or []

    if not interfaces:
        raise ValueError(
            "Selecione pelo menos uma interface."
        )

    validate_interface_description(
        description
    )

    if description is not None and remove_description:
        raise ValueError(
            "Informe uma descrição ou escolha remover "
            "a descrição, não as duas opções ao mesmo tempo."
        )

    if voice_vlan is not None and remove_voice_vlan:
        raise ValueError(
            "Informe uma Voice VLAN ou escolha remover "
            "a Voice VLAN, não as duas opções ao mesmo tempo."
        )

    if admin_state not in (
        None,
        "up",
        "down",
    ):
        raise ValueError(
            "Estado administrativo deve ser 'up' ou 'down'."
        )

    if portfast_state not in (
        None,
        "enable",
        "disable",
    ):
        raise ValueError(
            "PortFast deve ser 'enable', 'disable' ou não informado."
        )


    has_configuration = (
        access_vlan is not None
        or voice_vlan is not None
        or remove_voice_vlan
        or description is not None
        or remove_description
        or admin_state is not None
        or portfast_state is not None
    )

    if not has_configuration:
        raise ValueError(
            "Informe pelo menos uma configuração "
            "para as interfaces selecionadas."
        )

    switch = CiscoSwitch(
        host=host,
        username=username,
        password=password,
        secret=secret,
    )

    output, validation, running_config = (
        switch.configure_interfaces(
            interfaces=interfaces,
            access_vlan=access_vlan,
            voice_vlan=voice_vlan,
            remove_voice_vlan=remove_voice_vlan,
            description=description,
            remove_description=remove_description,
            admin_state=admin_state,
            portfast_state=portfast_state,
        )
    )

    missing = []
    changes = []
    interface_results = {}

    for interface in interfaces:
        state = validation[interface][
            "interface_state"
        ]

        running_interface = validation[
            interface
        ]["running_config"]

        stp_detail = validation[
            interface
        ].get("stp_detail", "")

        interface_missing = []

        has_switchport_config = (
            access_vlan is not None
            or voice_vlan is not None
            or remove_voice_vlan
        )

        if has_switchport_config:
            if (
                "Administrative Mode: static access"
                not in state
            ):
                interface_missing.append(
                    "mode-access"
                )

        if access_vlan is not None:
            marker = (
                f"Access Mode VLAN: {access_vlan}"
            )

            if marker not in state:
                interface_missing.append(
                    f"access-vlan:{access_vlan}"
                )

        if voice_vlan is not None:
            marker = (
                f"Voice VLAN: {voice_vlan}"
            )

            if marker not in state:
                interface_missing.append(
                    f"voice-vlan:{voice_vlan}"
                )

        if remove_voice_vlan:
            if "Voice VLAN: none" not in state:
                interface_missing.append(
                    "remove-voice-vlan"
                )

        running_lines = [
            line.strip()
            for line in running_interface.splitlines()
        ]

        if description is not None:
            marker = (
                f"description {description}"
            )

            if marker not in running_lines:
                interface_missing.append(
                    "description"
                )

        if remove_description:
            if any(
                line.startswith(
                    "description "
                )
                for line in running_lines
            ):
                interface_missing.append(
                    "remove-description"
                )

        if admin_state == "down":
            if (
                "administratively down"
                not in state.lower()
            ):
                interface_missing.append(
                    "admin-down"
                )

        if admin_state == "up":
            if (
                "administratively down"
                in state.lower()
            ):
                interface_missing.append(
                    "admin-up"
                )

        interface_admin_down = (
            "administratively down"
            in state.lower()
        )

        if portfast_state == "enable":
            if (
                "spanning-tree portfast edge"
                not in running_interface.lower()
            ):
                interface_missing.append(
                    "portfast-edge"
                )

            # Com a interface administrativamente desativada,
            # o running-config confirma a intenção configurada.
            # A ausência de estado operacional STP não é divergência.
            if (
                not interface_admin_down
                and stp_detail
                and "portfast edge mode"
                not in stp_detail.lower()
            ):
                interface_missing.append(
                    "portfast-edge-operational"
                )

        if portfast_state == "disable":
            if (
                "spanning-tree portfast disable"
                not in running_interface.lower()
            ):
                interface_missing.append(
                    "portfast-disable"
                )

            if (
                not interface_admin_down
                and stp_detail
                and "portfast edge mode"
                in stp_detail.lower()
            ):
                interface_missing.append(
                    "portfast-disable-operational"
                )

        for item in interface_missing:
            missing.append(
                f"interface:{interface}:{item}"
            )

        summary = summarize_interface_state(
            state
        )

        interface_results[interface] = {
            "success": not interface_missing,
            "missing": interface_missing,
            "summary": summary,
            "summary_highlighted": (
                highlight_interface_counters(
                    summary
                )
            ),
            "health": classify_interface_health(
                state
            ),
        }

        if description is not None:
            changes.append(
                f"{interface}: Description {description}"
            )

        if remove_description:
            changes.append(
                f"{interface}: Description removida"
            )

        if access_vlan is not None:
            changes.append(
                f"{interface}: Access VLAN {access_vlan}"
            )

        if voice_vlan is not None:
            changes.append(
                f"{interface}: Voice VLAN {voice_vlan}"
            )

        if remove_voice_vlan:
            changes.append(
                f"{interface}: Voice VLAN removida"
            )

        if admin_state == "up":
            changes.append(
                f"{interface}: Admin Up"
            )

        if admin_state == "down":
            changes.append(
                f"{interface}: Admin Down"
            )

        if portfast_state == "enable":
            changes.append(
                f"{interface}: PortFast Edge habilitado"
            )

        if portfast_state == "disable":
            changes.append(
                f"{interface}: PortFast desabilitado"
            )

    backup = save_backup(
        None,
        running_config,
    )

    change_groups = []

    for interface in interfaces:
        interface_changes = []

        prefix = f"{interface}: "

        for change in changes:
            if change.startswith(prefix):
                interface_changes.append(
                    change[len(prefix):]
                )

        if interface_changes:
            change_groups.append(
                {
                    "interface": interface,
                    "changes": interface_changes,
                }
            )

    return {
        "success": not missing,
        "missing": missing,
        "changes": changes,
        "change_groups": change_groups,
        "backup": str(backup),
        "configuration_output": output,
        "interface_results": interface_results,
        "interfaces": interfaces,
    }


def get_switch_svis(
    host,
    username,
    password,
    secret="",
):
    switch = CiscoSwitch(
        host=host,
        username=username,
        password=password,
        secret=secret,
    )

    return switch.list_svis()


def run_switch_ping(
    host,
    username,
    password,
    source_interface,
    targets,
    secret="",
    repeat=5,
    timeout=2,
):
    from src.switch.troubleshooting import (
        parse_ipv4_targets,
        parse_ping_result,
        validate_source_svi,
    )

    switch = CiscoSwitch(
        host=host,
        username=username,
        password=password,
        secret=secret,
    )

    svi_inventory = switch.list_svis()
    svis = svi_inventory["svis"]

    source = validate_source_svi(
        svis,
        source_interface,
    )

    destinations = parse_ipv4_targets(
        targets
        if isinstance(targets, str)
        else ",".join(targets)
    )

    results = []

    for destination in destinations:
        execution = switch.ping(
            destination=destination,
            source_interface=source["name"],
            repeat=repeat,
            timeout=timeout,
        )

        parsed = parse_ping_result(
            execution["output"]
        )

        results.append(
            {
                "destination": destination,
                "source_interface": source["name"],
                "source_ip": source["ip_address"],
                "command": execution["command"],
                "output": execution["output"],
                **parsed,
            }
        )

    return {
        "source": source,
        "count": len(results),
        "results": results,
    }


def run_switch_traceroute(
    host,
    username,
    password,
    source_interface,
    destination,
    secret="",
):
    from src.switch.troubleshooting import (
        parse_ipv4_targets,
        validate_source_svi,
    )

    switch = CiscoSwitch(
        host=host,
        username=username,
        password=password,
        secret=secret,
    )

    svi_inventory = switch.list_svis()
    svis = svi_inventory["svis"]

    source = validate_source_svi(
        svis,
        source_interface,
    )

    destinations = parse_ipv4_targets(
        destination,
        max_targets=1,
    )

    target = destinations[0]

    execution = switch.traceroute(
        destination=target,
        source_ip=source["ip_address"],
    )

    return {
        "destination": target,
        "source_interface": source["name"],
        "source_ip": source["ip_address"],
        "mode": execution["mode"],
        "output": execution["output"],
    }
