from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

ALLOWED_CONFIG_EXTENSIONS = {
    ".cfg",
    ".conf",
    ".txt",
}


VOLATILE_PATTERNS = (
    re.compile(
        r"^Building configuration\.\.\.$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^Current configuration\s*:\s*\d+\s+bytes$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^Using\s+\d+\s+out of\s+\d+\s+bytes.*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^!\s*Last configuration change.*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^!\s*NVRAM config last updated.*$",
        re.IGNORECASE,
    ),
)


@dataclass(frozen=True)
class ConfigDiffRow:
    startup_line: str | None
    running_line: str | None
    status: str


@dataclass(frozen=True)
class ConfigSectionDiff:
    name: str
    status: str
    startup_lines: tuple[str, ...]
    running_lines: tuple[str, ...]
    removed_lines: tuple[str, ...]
    added_lines: tuple[str, ...]
    rows: tuple[ConfigDiffRow, ...]


@dataclass(frozen=True)
class ConfigComparison:
    left_label: str
    right_label: str
    changed_sections: tuple[ConfigSectionDiff, ...]
    added_lines: int
    removed_lines: int

    @property
    def identical(self):
        return not self.changed_sections

    @property
    def changed_count(self):
        return len(
            self.changed_sections
        )


def normalize_config_text(value):
    if value is None:
        return ""

    text = value.replace(
        "\r\n",
        "\n",
    ).replace(
        "\r",
        "\n",
    )

    cleaned = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()

        if any(
            pattern.match(line)
            for pattern in VOLATILE_PATTERNS
        ):
            continue

        cleaned.append(line)

    while cleaned and not cleaned[0].strip():
        cleaned.pop(0)

    while cleaned and not cleaned[-1].strip():
        cleaned.pop()

    return (
        "\n".join(cleaned)
        + ("\n" if cleaned else "")
    )


def extract_hostname(config_text):
    for raw_line in config_text.splitlines():
        line = raw_line.strip()

        if line.startswith("hostname "):
            hostname = line.split(
                None,
                1,
            )[1].strip()

            if hostname:
                return hostname

    return "switch"


def validate_config_filename(filename):
    if not filename:
        raise ValueError(
            "Arquivo de configuração não informado."
        )

    suffix = Path(
        filename
    ).suffix.lower()

    if suffix not in ALLOWED_CONFIG_EXTENSIONS:
        raise ValueError(
            "Formato de arquivo inválido. "
            "Use .cfg, .conf ou .txt."
        )

    return True


def build_backup_filename(
    hostname,
    config_type,
    timestamp=None,
):
    timestamp = (
        timestamp
        or datetime.now()
    )

    safe_hostname = "".join(
        char
        if (
            char.isalnum()
            or char in "-_"
        )
        else "_"
        for char in hostname
    )

    return (
        f"{safe_hostname}_"
        f"{config_type}_"
        f"{timestamp:%Y%m%d_%H%M%S}.cfg"
    )


def _split_cisco_blocks(config_text):
    """
    Divide uma configuração Cisco em blocos sem gerar
    falsos positivos para comandos globais.

    Blocos hierárquicos:
      interface ...
      router ...
      line ...
      vlan ...
      policy-map ...
      etc.

    Todos os comandos globais são agrupados em um único
    bloco. Isso permite que comandos idênticos presentes
    em posições diferentes da running/startup continuem
    sendo reconhecidos como iguais.
    """
    text = normalize_config_text(
        config_text
    )

    hierarchical_prefixes = (
        "interface ",
        "router ",
        "line ",
        "class-map ",
        "policy-map ",
        "ip access-list ",
        "route-map ",
        "vlan ",
        "vrf ",
        "crypto ",
    )

    raw_blocks = []
    current = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()

        if line.strip() == "!":
            if current:
                raw_blocks.append(
                    tuple(current)
                )

                current = []

            continue

        if not line.strip():
            continue

        current.append(line)

    if current:
        raw_blocks.append(
            tuple(current)
        )

    blocks = {}
    global_lines = []
    occurrences = {}

    for block in raw_blocks:
        first = block[0].strip()

        hierarchical = first.startswith(
            hierarchical_prefixes
        )

        if not hierarchical:
            global_lines.extend(
                block
            )
            continue

        base_key = first

        count = occurrences.get(
            base_key,
            0,
        )

        occurrences[
            base_key
        ] = count + 1

        key = (
            base_key
            if count == 0
            else f"{base_key}#{count + 1}"
        )

        blocks[key] = {
            "name": first,
            "lines": block,
        }

    # Mantemos todos os comandos globais num bloco único.
    # Assim, por exemplo, "ip ssh version 2" não aparece
    # simultaneamente como removido e adicionado apenas
    # porque outro comando global foi inserido antes dele.
    if global_lines:
        blocks["__global__"] = {
            "name": "Configuração global",
            "lines": tuple(
                global_lines
            ),
        }

    return blocks

def _command_identity(line):
    command = line.strip()

    if command.startswith("no "):
        command = command[3:]

    rules = (
        (
            r"^switchport access vlan\s+",
            "switchport access vlan",
        ),
        (
            r"^switchport voice vlan\s+",
            "switchport voice vlan",
        ),
        (
            r"^switchport mode\s+",
            "switchport mode",
        ),
        (
            r"^switchport trunk allowed vlan\s+",
            "switchport trunk allowed vlan",
        ),
        (
            r"^switchport trunk native vlan\s+",
            "switchport trunk native vlan",
        ),
        (
            r"^spanning-tree portfast\s+",
            "spanning-tree portfast",
        ),
        (
            r"^spanning-tree guard\s+",
            "spanning-tree guard",
        ),
        (
            r"^description(?:\s+|$)",
            "description",
        ),
        (
            r"^ip address\s+",
            "ip address",
        ),
        (
            r"^ipv6 address\s+",
            "ipv6 address",
        ),
        (
            r"^mtu\s+",
            "mtu",
        ),
        (
            r"^channel-group\s+",
            "channel-group",
        ),
        (
            r"^speed\s+",
            "speed",
        ),
        (
            r"^duplex\s+",
            "duplex",
        ),
        (
            r"^shutdown$",
            "administrative-state",
        ),
        (
            r"^no shutdown$",
            "administrative-state",
        ),
    )

    for pattern, identity in rules:
        if re.match(
            pattern,
            command,
            re.IGNORECASE,
        ):
            return identity

    # Fallback genérico.
    #
    # Para comandos desconhecidos usa os primeiros tokens
    # como aproximação de identidade semântica.
    tokens = command.split()

    if len(tokens) >= 3:
        return " ".join(
            tokens[:3]
        )

    if len(tokens) >= 2:
        return " ".join(
            tokens[:2]
        )

    return command


def _align_changed_lines(
    removed_lines,
    added_lines,
):
    removed = list(
        removed_lines
    )

    added = list(
        added_lines
    )

    rows = []
    used_added = set()

    # Primeiro tenta parear comandos do mesmo tipo.
    for old_line in removed:
        old_identity = _command_identity(
            old_line
        )

        match_index = None

        for index, new_line in enumerate(
            added
        ):
            if index in used_added:
                continue

            if (
                _command_identity(
                    new_line
                )
                == old_identity
            ):
                match_index = index
                break

        if match_index is not None:
            new_line = added[
                match_index
            ]

            used_added.add(
                match_index
            )

            rows.append(
                ConfigDiffRow(
                    startup_line=old_line,
                    running_line=new_line,
                    status="changed",
                )
            )

        else:
            rows.append(
                ConfigDiffRow(
                    startup_line=old_line,
                    running_line=None,
                    status="removed",
                )
            )

    # Depois acrescenta comandos exclusivos da running.
    for index, new_line in enumerate(
        added
    ):
        if index in used_added:
            continue

        rows.append(
            ConfigDiffRow(
                startup_line=None,
                running_line=new_line,
                status="added",
            )
        )

    return tuple(
        rows
    )


def _changed_lines(
    startup_lines,
    running_lines,
):
    matcher = SequenceMatcher(
        None,
        startup_lines,
        running_lines,
        autojunk=False,
    )

    removed = []
    added = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in {
            "replace",
            "delete",
        }:
            removed.extend(
                startup_lines[i1:i2]
            )

        if tag in {
            "replace",
            "insert",
        }:
            added.extend(
                running_lines[j1:j2]
            )

    return (
        tuple(removed),
        tuple(added),
    )


def compare_cisco_configs(
    startup_text,
    running_text,
    left_label="startup-config",
    right_label="running-config",
):
    startup_blocks = _split_cisco_blocks(
        startup_text
    )

    running_blocks = _split_cisco_blocks(
        running_text
    )

    ordered_keys = list(
        startup_blocks
    )

    ordered_keys.extend(
        key
        for key in running_blocks
        if key not in startup_blocks
    )

    differences = []
    total_added = 0
    total_removed = 0

    for key in ordered_keys:
        startup = startup_blocks.get(
            key
        )

        running = running_blocks.get(
            key
        )

        if startup is None:
            added = tuple(
                running["lines"]
            )

            total_added += len(
                added
            )

            differences.append(
                ConfigSectionDiff(
                    name=running["name"],
                    status="running_only",
                    startup_lines=(),
                    running_lines=tuple(
                        running["lines"]
                    ),
                    removed_lines=(),
                    added_lines=added,
                    rows=tuple(
                        ConfigDiffRow(
                            startup_line=None,
                            running_line=line,
                            status="added",
                        )
                        for line in added
                    ),
                )
            )

            continue

        if running is None:
            removed = tuple(
                startup["lines"]
            )

            total_removed += len(
                removed
            )

            differences.append(
                ConfigSectionDiff(
                    name=startup["name"],
                    status="startup_only",
                    startup_lines=tuple(
                        startup["lines"]
                    ),
                    running_lines=(),
                    removed_lines=removed,
                    added_lines=(),
                    rows=tuple(
                        ConfigDiffRow(
                            startup_line=line,
                            running_line=None,
                            status="removed",
                        )
                        for line in removed
                    ),
                )
            )

            continue

        startup_lines = tuple(
            startup["lines"]
        )

        running_lines = tuple(
            running["lines"]
        )

        if startup_lines == running_lines:
            continue

        removed, added = _changed_lines(
            startup_lines,
            running_lines,
        )

        total_removed += len(
            removed
        )

        total_added += len(
            added
        )

        differences.append(
            ConfigSectionDiff(
                name=running["name"],
                status="modified",
                startup_lines=startup_lines,
                running_lines=running_lines,
                removed_lines=removed,
                added_lines=added,
                rows=_align_changed_lines(
                    removed,
                    added,
                ),
            )
        )

    return ConfigComparison(
        left_label=left_label,
        right_label=right_label,
        changed_sections=tuple(
            differences
        ),
        added_lines=total_added,
        removed_lines=total_removed,
    )
