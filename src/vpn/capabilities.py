from dataclasses import dataclass


@dataclass(frozen=True)
class IPsecCapabilities:
    ike_versions: tuple[int, ...]
    phase1_proposals: tuple[str, ...]
    phase1_dh_groups: tuple[int, ...]
    phase2_proposals: tuple[str, ...]
    phase2_dh_groups: tuple[int, ...]


def intersect_capabilities(
    fortigate: IPsecCapabilities,
    paloalto: IPsecCapabilities,
) -> IPsecCapabilities:
    return IPsecCapabilities(
        ike_versions=tuple(
            sorted(set(fortigate.ike_versions) & set(paloalto.ike_versions))
        ),
        phase1_proposals=tuple(
            sorted(set(fortigate.phase1_proposals) & set(paloalto.phase1_proposals))
        ),
        phase1_dh_groups=tuple(
            sorted(set(fortigate.phase1_dh_groups) & set(paloalto.phase1_dh_groups))
        ),
        phase2_proposals=tuple(
            sorted(set(fortigate.phase2_proposals) & set(paloalto.phase2_proposals))
        ),
        phase2_dh_groups=tuple(
            sorted(set(fortigate.phase2_dh_groups) & set(paloalto.phase2_dh_groups))
        ),
    )


def validate_selected_capabilities(
    *,
    selected: IPsecCapabilities,
    supported: IPsecCapabilities,
) -> None:
    checks = (
        (
            selected.ike_versions,
            supported.ike_versions,
            "IKE Version",
        ),
        (
            selected.phase1_proposals,
            supported.phase1_proposals,
            "Phase1 Proposal",
        ),
        (
            selected.phase1_dh_groups,
            supported.phase1_dh_groups,
            "Phase1 DH Group",
        ),
        (
            selected.phase2_proposals,
            supported.phase2_proposals,
            "Phase2 Proposal",
        ),
        (
            selected.phase2_dh_groups,
            supported.phase2_dh_groups,
            "Phase2 DH Group",
        ),
    )

    for requested, available, label in checks:
        for value in requested:
            if value not in available:
                raise ValueError(
                    f"{label} nao suportado simultaneamente "
                    f"por FortiGate e Palo Alto: {value}"
                )
