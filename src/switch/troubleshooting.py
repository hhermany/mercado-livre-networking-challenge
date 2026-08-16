from ipaddress import IPv4Address


def parse_l3_interfaces(output):
    """
    Parseia 'show ip interface brief' e retorna interfaces
    Layer 3 IPv4 com endereço configurado.

    Inclui interfaces físicas routed, SVIs e outros tipos
    que possuam IPv4 válido. O estado operacional é
    preservado para permitir filtragem posterior.
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

        if ip_address.lower() == "unassigned":
            continue

        try:
            IPv4Address(ip_address)
        except ValueError:
            continue

        protocol = fields[-1]
        status = " ".join(fields[4:-1])

        operational = status.lower() == "up" and protocol.lower() == "up"

        interfaces.append(
            {
                "name": interface,
                "ip_address": ip_address,
                "status": status,
                "protocol": protocol,
                "operational": operational,
                "label": (f"{interface} - {ip_address}"),
            }
        )

    return interfaces


def _parse_ipv4(value):
    try:
        return IPv4Address(value.strip())
    except ValueError as exc:
        raise ValueError(f"Endereço IPv4 inválido: {value}") from exc


def _expand_ipv4_range(value):
    start_text, separator, end_text = value.partition("-")

    if not separator:
        return [str(_parse_ipv4(value))]

    if "-" in end_text:
        raise ValueError(f"Range IPv4 inválido: {value}")

    start = _parse_ipv4(start_text)
    end = _parse_ipv4(end_text)

    if int(end) < int(start):
        raise ValueError(f"Range IPv4 invertido: {value}")

    return [
        str(IPv4Address(address))
        for address in range(
            int(start),
            int(end) + 1,
        )
    ]


def split_targets_for_workers(
    targets,
    workers,
):
    """
    Divide destinos em lotes contíguos e equilibrados.

    A ordem original é preservada quando os resultados
    dos lotes são concatenados posteriormente.
    """
    if workers < 1:
        raise ValueError("A concorrência deve ser maior que zero.")

    if not targets:
        return []

    worker_count = min(
        workers,
        len(targets),
    )

    base_size, remainder = divmod(
        len(targets),
        worker_count,
    )

    chunks = []
    start = 0

    for index in range(worker_count):
        size = base_size + (1 if index < remainder else 0)

        end = start + size

        chunks.append(targets[start:end])

        start = end

    return chunks


def parse_ipv4_targets(
    value,
    max_targets=None,
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
        raise ValueError("Informe pelo menos um destino.")

    if max_targets is not None and max_targets < 1:
        raise ValueError("O limite de destinos deve ser maior que zero.")

    targets = []
    seen = set()

    entries = [item.strip() for item in value.split(",") if item.strip()]

    if not entries:
        raise ValueError("Informe pelo menos um destino.")

    for entry in entries:
        for target in _expand_ipv4_range(entry):
            if target in seen:
                continue

            targets.append(target)
            seen.add(target)

            if max_targets is not None and len(targets) > max_targets:
                raise ValueError(
                    "Quantidade de destinos excede o limite "
                    f"de {max_targets} endereços."
                )

    return targets


def find_l3_interface_by_name(
    interfaces,
    interface_name,
):
    for interface in interfaces:
        if interface["name"].lower() == interface_name.lower():
            return interface

    raise ValueError(f"Interface L3 {interface_name} não encontrada.")


def validate_source_interface(
    interfaces,
    interface_name,
):
    interface = find_l3_interface_by_name(
        interfaces,
        interface_name,
    )

    if not interface["operational"]:
        raise ValueError(
            f"A interface L3 {interface['name']} não está operacional (up/up)."
        )

    return interface


def extract_traceroute_result(output):
    if not output:
        return ""

    lines = output.splitlines()

    # Preferimos começar no bloco efetivamente operacional.
    start_index = None

    for index, line in enumerate(lines):
        if line.strip().startswith("VRF info:"):
            start_index = index
            break

    # Alguns IOS não imprimem VRF info.
    # Nesse caso procuramos o primeiro hop.
    if start_index is None:
        for index, line in enumerate(lines):
            stripped = line.strip()

            if stripped and stripped[0].isdigit() and "Protocol [" not in stripped:
                start_index = index
                break

    # Fallback: a partir de "Tracing the route".
    if start_index is None:
        for index, line in enumerate(lines):
            if "Tracing the route" in line:
                start_index = index
                break

    if start_index is None:
        return output.strip()

    useful_lines = lines[start_index:]

    # Remove prompt final do equipamento, se vier junto.
    while useful_lines:
        last = useful_lines[-1].strip()

        if not last:
            useful_lines.pop()
            continue

        if last.endswith("#") or last.endswith(">"):
            useful_lines.pop()
            continue

        break

    return "\n".join(useful_lines).strip()


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

    success_rate = int(success_match.group(1))

    result = {
        "success": success_rate > 0,
        "success_rate": success_rate,
        "received": int(success_match.group(2)),
        "sent": int(success_match.group(3)),
        "rtt_min_ms": None,
        "rtt_avg_ms": None,
        "rtt_max_ms": None,
    }

    if rtt_match:
        result.update(
            {
                "rtt_min_ms": int(rtt_match.group(1)),
                "rtt_avg_ms": int(rtt_match.group(2)),
                "rtt_max_ms": int(rtt_match.group(3)),
            }
        )

    return result
