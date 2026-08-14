from ipaddress import IPv4Address

DEFAULT_MAX_TARGETS = 64


def parse_svi_interfaces(output):
    """
    Parseia 'show ip interface brief' e retorna somente SVIs
    com endereço IPv4 configurado.
    """
    interfaces = []

    for raw_line in output.splitlines():
        line = raw_line.strip()

        if not line or line.startswith("Interface "):
            continue

        fields = line.split()

        if len(fields) < 6:
            continue

        interface = fields[0]
        ip_address = fields[1]

        if not interface.lower().startswith("vlan"):
            continue

        if ip_address.lower() == "unassigned":
            continue

        try:
            IPv4Address(ip_address)
        except ValueError:
            continue

        # O campo Status pode conter "administratively down".
        protocol = fields[-1]
        status = " ".join(fields[4:-1])

        interfaces.append(
            {
                "name": interface,
                "ip_address": ip_address,
                "status": status,
                "protocol": protocol,
                "operational": (
                    status.lower() == "up"
                    and protocol.lower() == "up"
                ),
                "label": (
                    f"{interface} - {ip_address}"
                ),
            }
        )

    return interfaces


def _parse_ipv4(value):
    try:
        return IPv4Address(value.strip())
    except ValueError as exc:
        raise ValueError(
            f"Endereço IPv4 inválido: {value}"
        ) from exc


def _expand_ipv4_range(value):
    start_text, separator, end_text = value.partition("-")

    if not separator:
        return [str(_parse_ipv4(value))]

    if "-" in end_text:
        raise ValueError(
            f"Range IPv4 inválido: {value}"
        )

    start = _parse_ipv4(start_text)
    end = _parse_ipv4(end_text)

    if int(end) < int(start):
        raise ValueError(
            f"Range IPv4 invertido: {value}"
        )

    return [
        str(IPv4Address(address))
        for address in range(
            int(start),
            int(end) + 1,
        )
    ]


def parse_ipv4_targets(
    value,
    max_targets=DEFAULT_MAX_TARGETS,
):
    """
    Aceita:
      8.8.8.8
      8.8.8.8,1.1.1.1
      192.168.10.1-192.168.10.5
      combinação de IPs e ranges.

    Remove duplicatas preservando a ordem.
    """
    if value is None or not value.strip():
        raise ValueError(
            "Informe pelo menos um destino."
        )

    if max_targets < 1:
        raise ValueError(
            "O limite de destinos deve ser maior que zero."
        )

    targets = []
    seen = set()

    entries = [
        item.strip()
        for item in value.split(",")
        if item.strip()
    ]

    if not entries:
        raise ValueError(
            "Informe pelo menos um destino."
        )

    for entry in entries:
        for target in _expand_ipv4_range(entry):
            if target in seen:
                continue

            targets.append(target)
            seen.add(target)

            if len(targets) > max_targets:
                raise ValueError(
                    "Quantidade de destinos excede o limite "
                    f"de {max_targets} endereços."
                )

    return targets


def find_svi_by_name(svis, interface_name):
    for svi in svis:
        if svi["name"].lower() == interface_name.lower():
            return svi

    raise ValueError(
        f"SVI {interface_name} não encontrada."
    )


def validate_source_svi(svis, interface_name):
    svi = find_svi_by_name(
        svis,
        interface_name,
    )

    if not svi["operational"]:
        raise ValueError(
            f"A SVI {svi['name']} não está operacional "
            "(up/up)."
        )

    return svi


def parse_ping_result(output):
    import re

    success_match = re.search(
        r"Success rate is\s+(\d+)\s+percent\s+"
        r"\((\d+)/(\d+)\)",
        output,
        re.IGNORECASE,
    )

    rtt_match = re.search(
        r"round-trip min/avg/max\s*=\s*"
        r"(\d+)/(\d+)/(\d+)\s+ms",
        output,
        re.IGNORECASE,
    )

    if success_match is None:
        return {
            "success": False,
            "success_rate": None,
            "received": None,
            "sent": None,
            "rtt_min_ms": None,
            "rtt_avg_ms": None,
            "rtt_max_ms": None,
        }

    success_rate = int(
        success_match.group(1)
    )

    result = {
        "success": success_rate > 0,
        "success_rate": success_rate,
        "received": int(
            success_match.group(2)
        ),
        "sent": int(
            success_match.group(3)
        ),
        "rtt_min_ms": None,
        "rtt_avg_ms": None,
        "rtt_max_ms": None,
    }

    if rtt_match:
        result.update(
            {
                "rtt_min_ms": int(
                    rtt_match.group(1)
                ),
                "rtt_avg_ms": int(
                    rtt_match.group(2)
                ),
                "rtt_max_ms": int(
                    rtt_match.group(3)
                ),
            }
        )

    return result
