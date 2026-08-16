from difflib import unified_diff


def build_candidate_diff(
    running_config,
    candidate_config,
):
    """
    Diff textual somente para revisão humana.

    Nesta fase não representa intenção de remoção automática.
    Nenhum comando 'no ...' é derivado deste diff.
    """
    running_lines = str(running_config or "").strip().splitlines()

    candidate_lines = str(candidate_config or "").strip().splitlines()

    return "\n".join(
        unified_diff(
            running_lines,
            candidate_lines,
            fromfile="running-config",
            tofile="candidate-config",
            lineterm="",
        )
    )
