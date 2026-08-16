def _interface_names(interfaces):
    return [item["name"] for item in interfaces]


def select_interface_range(
    interfaces,
    start_interface,
    end_interface,
):
    if not start_interface or not end_interface:
        raise ValueError("Informe a interface inicial e a interface final.")

    names = _interface_names(interfaces)

    if start_interface not in names:
        raise ValueError(
            f"A interface inicial {start_interface} não foi encontrada no switch."
        )

    if end_interface not in names:
        raise ValueError(
            f"A interface final {end_interface} não foi encontrada no switch."
        )

    start_index = names.index(start_interface)
    end_index = names.index(end_interface)

    if start_index > end_index:
        raise ValueError(
            "A interface inicial deve aparecer antes da interface final no equipamento."
        )

    return interfaces[start_index : end_index + 1]


def select_specific_interfaces(
    interfaces,
    selected_names,
):
    selected_names = selected_names or []

    inventory_names = _interface_names(interfaces)

    unknown = [name for name in selected_names if name not in inventory_names]

    if unknown:
        raise ValueError("Interfaces não encontradas no switch: " + ", ".join(unknown))

    selected_set = set(selected_names)

    return [item for item in interfaces if item["name"] in selected_set]


def combine_interface_selection(
    interfaces,
    selected_names=None,
    start_interface=None,
    end_interface=None,
):
    selected_names = selected_names or []

    selected = []

    if selected_names:
        selected.extend(
            select_specific_interfaces(
                interfaces=interfaces,
                selected_names=selected_names,
            )
        )

    has_start = bool(start_interface)
    has_end = bool(end_interface)

    if has_start != has_end:
        raise ValueError(
            "Para usar um range, informe a interface inicial e a interface final."
        )

    if has_start and has_end:
        selected.extend(
            select_interface_range(
                interfaces=interfaces,
                start_interface=start_interface,
                end_interface=end_interface,
            )
        )

    if not selected:
        raise ValueError("Selecione pelo menos uma interface ou informe um range.")

    selected_names_set = {item["name"] for item in selected}

    # Retorna sempre na ordem real do inventário do equipamento
    # e elimina interfaces duplicadas automaticamente.
    return [item for item in interfaces if item["name"] in selected_names_set]


def _build_interface_preview(item):
    warnings = []

    vlan = item.get("vlan", "")
    status = item.get("status", "")
    description = item.get("description", "")

    if vlan.lower() == "routed":
        warnings.append("Interface Layer 3 (routed)")

    if vlan.lower() == "trunk":
        warnings.append("Interface trunk")

    if status == "connected":
        warnings.append("Interface está conectada")

    if description:
        warnings.append("Interface possui descrição")

    return {
        **item,
        "warnings": warnings,
    }


def build_selection_preview(
    interfaces,
    selected_names=None,
    start_interface=None,
    end_interface=None,
):
    selected = combine_interface_selection(
        interfaces=interfaces,
        selected_names=selected_names,
        start_interface=start_interface,
        end_interface=end_interface,
    )

    preview_interfaces = [_build_interface_preview(item) for item in selected]

    return {
        "count": len(preview_interfaces),
        "interfaces": preview_interfaces,
        "names": [item["name"] for item in preview_interfaces],
        "has_warnings": any(item["warnings"] for item in preview_interfaces),
    }


def build_batch_preview(
    interfaces,
    start_interface,
    end_interface,
):
    selected = select_interface_range(
        interfaces=interfaces,
        start_interface=start_interface,
        end_interface=end_interface,
    )

    preview_interfaces = [_build_interface_preview(item) for item in selected]

    return {
        "count": len(preview_interfaces),
        "start_interface": start_interface,
        "end_interface": end_interface,
        "interfaces": preview_interfaces,
        "has_warnings": any(item["warnings"] for item in preview_interfaces),
    }
