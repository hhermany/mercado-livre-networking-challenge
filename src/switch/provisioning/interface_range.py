import re
from dataclasses import dataclass

_INTERFACE_PATTERN = re.compile(
    r"^(?P<type>[A-Za-z][A-Za-z-]*)(?P<numbers>\d+(?:/\d+)*)$"
)


@dataclass(frozen=True)
class ParsedInterface:
    original: str
    interface_type: str
    hierarchy: tuple[int, ...]
    port: int


def parse_interface_name(
    interface_name,
):
    """
    Interpreta formatos como:

    Gi1
    Gi0/1
    Gi1/1
    Gi1/0/1
    GigabitEthernet1/0/48

    A última posição numérica representa a porta.
    Tudo antes dela representa a hierarquia.
    """
    value = str(interface_name or "").strip()

    match = _INTERFACE_PATTERN.match(value)

    if not match:
        return None

    numbers = tuple(int(part) for part in match.group("numbers").split("/"))

    if not numbers:
        return None

    return ParsedInterface(
        original=value,
        interface_type=match.group("type"),
        hierarchy=numbers[:-1],
        port=numbers[-1],
    )


def _full_interface_name(
    parsed,
    port,
):
    numbers = (
        *parsed.hierarchy,
        port,
    )

    return parsed.interface_type + "/".join(str(number) for number in numbers)


def _build_group(
    run,
):
    """
    Transforma uma sequência contínua já validada
    em interface individual ou interface range.
    """
    if not run:
        return None

    if len(run) == 1:
        item = run[0]

        return {
            "mode": "single",
            "interfaces": [item.original],
            "command": (f"interface {item.original}"),
        }

    first = run[0]
    last = run[-1]

    first_name = _full_interface_name(
        first,
        first.port,
    )

    return {
        "mode": "range",
        "interfaces": [item.original for item in run],
        "command": (f"interface range {first_name} - {last.port}"),
    }


def build_interface_groups(
    interfaces,
):
    """
    Cria ranges somente usando interfaces efetivamente
    encontradas no inventário.

    Regras:

    - não presume 24/48 portas;
    - não inventa portas ausentes;
    - não cruza slot/subslot;
    - não mistura tipos de interface;
    - suporta Gi1, Gi0/1, Gi1/1, Gi1/0/1 etc.;
    - interfaces não reconhecidas permanecem individuais.
    """
    unique_interfaces = list(
        dict.fromkeys(
            str(interface).strip() for interface in interfaces if str(interface).strip()
        )
    )

    parsed_groups = {}
    unparsed = []

    for interface in unique_interfaces:
        parsed = parse_interface_name(interface)

        if parsed is None:
            unparsed.append(interface)
            continue

        key = (
            parsed.interface_type.lower(),
            parsed.hierarchy,
        )

        parsed_groups.setdefault(key, []).append(parsed)

    result = []

    for parsed_interfaces in parsed_groups.values():
        parsed_interfaces = sorted(
            parsed_interfaces,
            key=lambda item: item.port,
        )

        run = []

        for parsed in parsed_interfaces:
            if not run:
                run.append(parsed)
                continue

            previous = run[-1]

            if parsed.port == previous.port + 1:
                run.append(parsed)
                continue

            group = _build_group(run)

            if group:
                result.append(group)

            run = [parsed]

        group = _build_group(run)

        if group:
            result.append(group)

    for interface in unparsed:
        result.append(
            {
                "mode": "single",
                "interfaces": [interface],
                "command": (f"interface {interface}"),
            }
        )

    return result
