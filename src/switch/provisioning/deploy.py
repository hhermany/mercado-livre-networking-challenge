from dataclasses import dataclass


@dataclass(frozen=True)
class CandidateConfigBlock:
    index: int
    commands: tuple[str, ...]

    @property
    def first_command(self):
        if not self.commands:
            return ""

        return self.commands[0]


def split_candidate_blocks(config_text):
    """
    Divide o Candidate em blocos Cisco independentes.

    O '!' é delimitador entre contextos de configuração.

    Exemplos:
        aaa group server radius RAD
         server name RAD1
         server name RAD2

        interface Vlan255
         description ...
         ip address ...

    Nenhum comando é enviado ao equipamento aqui.
    """
    blocks = []
    current = []

    def flush():
        if not current:
            return

        blocks.append(
            CandidateConfigBlock(
                index=len(blocks) + 1,
                commands=tuple(current),
            )
        )

        current.clear()

    for raw_line in str(config_text or "").splitlines():
        stripped = raw_line.strip()

        if not stripped:
            continue

        if stripped.startswith("!"):
            flush()
            continue

        if stripped.lower() in {
            "configure terminal",
            "conf t",
            "end",
        }:
            continue

        current.append(stripped)

    flush()

    return blocks


def candidate_command_count(config_text):
    return sum(len(block.commands) for block in split_candidate_blocks(config_text))
