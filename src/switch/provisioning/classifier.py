import ipaddress
import re

from src.switch.provisioning.models import (
    InterfaceClassification,
)

PROVISION_NETWORK = ipaddress.ip_network("172.28.255.0/24")


_PHYSICAL_INTERFACE_PATTERN = re.compile(
    r"^(?:"
    r"Gi|GigabitEthernet|"
    r"Fa|FastEthernet|"
    r"Te|TenGigabitEthernet|"
    r"Twe|TwentyFiveGigE|"
    r"Hu|HundredGigE|"
    r"Eth|Ethernet"
    r")"
    r"\d+(?:/\d+)*$",
    re.IGNORECASE,
)


def _interface_name(
    interface,
):
    if not isinstance(
        interface,
        dict,
    ):
        return str(interface or "").strip()

    return str(
        interface.get("interface")
        or interface.get("name")
        or interface.get("port")
        or ""
    ).strip()


def _normalized_text(
    value,
):
    return str(value or "").strip().lower()


def _is_physical_interface(
    name,
):
    return bool(_PHYSICAL_INTERFACE_PATTERN.match(str(name or "").strip()))


def _physical_sort_key(
    name,
):
    """
    Ordenação pela hierarquia numérica da interface.

    Exemplos:
        Gi0
        Gi1
        Gi0/1
        Gi0/2
        Gi1/0/1
        Gi1/0/2
    """
    numbers = tuple(
        int(value)
        for value in re.findall(
            r"\d+",
            name,
        )
    )

    return numbers


def discover_provision_port(
    interfaces,
):
    """
    Retorna o registro completo da primeira interface física
    encontrada no inventário real.
    """
    candidates = []

    for interface in interfaces:
        name = _interface_name(interface)

        if not name:
            continue

        if not _is_physical_interface(name):
            continue

        candidates.append(interface)

    if not candidates:
        raise ValueError("Nenhuma interface física encontrada para Provision Port.")

    return sorted(
        candidates,
        key=lambda interface: _physical_sort_key(_interface_name(interface)),
    )[0]


def provision_port_ip(
    interface,
):
    """
    Tenta obter o endereço IPv4 de gerenciamento a partir
    dos campos que já podem existir no inventário.

    Aceita formatos:
        172.28.255.10
        172.28.255.10/24
    """
    for key in (
        "ip_address",
        "ip",
        "address",
        "ipv4",
    ):
        raw_value = str(
            interface.get(
                key,
                "",
            )
            or ""
        ).strip()

        if not raw_value:
            continue

        value = raw_value.split()[0]

        try:
            if "/" in value:
                return str(ipaddress.ip_interface(value).ip)

            return str(ipaddress.ip_address(value))

        except ValueError:
            continue

    return None


def validate_provision_port(
    interface,
):
    """
    Valida a invariante operacional da Provision Port.

    Ela precisa:
    - ser interface física;
    - estar em modo ROUTED;
    - possuir IPv4 em 172.28.255.0/24.

    Retorna dados estruturados para API/UX.
    """
    name = _interface_name(interface)

    mode = _normalized_text(
        interface.get("mode") or interface.get("mode_label") or interface.get("vlan")
    )

    ip_address = provision_port_ip(interface)

    is_routed = "routed" in mode

    in_provision_network = False

    if ip_address:
        try:
            in_provision_network = ipaddress.ip_address(ip_address) in PROVISION_NETWORK
        except ValueError:
            in_provision_network = False

    errors = []

    if not is_routed:
        errors.append((f"{name} não está em modo ROUTED."))

    if not ip_address:
        errors.append((f"{name} não possui IPv4 detectado."))

    elif not in_provision_network:
        errors.append((f"{name} possui IP {ip_address}, fora da rede 172.28.255.0/24."))

    return {
        "interface": name,
        "mode": ("ROUTED" if is_routed else mode.upper()),
        "ip_address": ip_address,
        "network": "172.28.255.0/24",
        "valid": (not errors),
        "errors": errors,
    }


def classify_interfaces(
    interfaces,
    *,
    uplink_interface,
):
    """
    Classifica o inventário em:

    - provision_port
    - uplink
    - user_ports
    - preserved_ports

    A Provision Port é sempre preservada.
    """
    uplink_interface = str(uplink_interface or "").strip()

    if not uplink_interface:
        raise ValueError("Informe a interface de uplink.")

    names = {
        _interface_name(interface)
        for interface in interfaces
        if _interface_name(interface)
    }

    if uplink_interface not in names:
        raise ValueError(
            "A interface de uplink não existe no inventário do equipamento."
        )

    provision_interface = discover_provision_port(interfaces)

    provision_validation = validate_provision_port(provision_interface)

    provision_name = provision_validation["interface"]

    if not provision_validation["valid"]:
        raise ValueError(
            ("Provision Port inválida: " + " ".join(provision_validation["errors"]))
        )

    if uplink_interface == provision_name:
        raise ValueError("A Provision Port não pode ser utilizada como uplink.")

    user_ports = []
    preserved_ports = [provision_name]

    for interface in interfaces:
        name = _interface_name(interface)

        if not name:
            continue

        if name in {
            provision_name,
            uplink_interface,
        }:
            continue

        mode = _normalized_text(
            interface.get("mode")
            or interface.get("mode_label")
            or interface.get("vlan")
        )

        port_channel = _normalized_text(interface.get("port_channel"))

        etherchannel = _normalized_text(interface.get("etherchannel"))

        lowered_name = name.lower()

        is_port_channel = lowered_name.startswith(
            "port-channel"
        ) or lowered_name.startswith("po")

        is_routed = "routed" in mode

        is_etherchannel_member = port_channel not in {
            "",
            "-",
            "none",
            "não",
            "nao",
        } or etherchannel not in {
            "",
            "-",
            "none",
            "não",
            "nao",
        }

        if (
            not _is_physical_interface(name)
            or is_port_channel
            or is_routed
            or is_etherchannel_member
        ):
            preserved_ports.append(name)
            continue

        user_ports.append(name)

    return InterfaceClassification(
        uplink=uplink_interface,
        provision_port=(provision_name),
        provision_ip=(provision_validation["ip_address"]),
        user_ports=user_ports,
        preserved_ports=list(dict.fromkeys(preserved_ports)),
    )
