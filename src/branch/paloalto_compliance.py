from dataclasses import dataclass

from src.branch.paloalto_contract import (
    build_paloalto_branch_plan,
)


@dataclass(frozen=True)
class PaloAltoComplianceReport:
    checks: tuple

    @property
    def success(self):
        return all(result for _, result, _ in self.checks)

    def render(self):
        lines = [
            "PALO ALTO GOLDEN COMPLIANCE",
            "",
        ]

        failures = 0

        for name, success, detail in self.checks:
            status = "OK" if success else "FALHOU"

            lines.append(f"{name:<30} {status}")

            if not success:
                failures += 1

                if detail:
                    lines.append(f"  -> {detail}")

        lines.extend(
            [
                "",
                (f"Unexpected differences: {failures}"),
                "",
                ("COMPLIANCE: " + ("VERDE" if failures == 0 else "VERMELHO")),
            ]
        )

        return "\n".join(lines)


class PaloAltoGoldenCompliance:
    def evaluate(
        self,
        *,
        candidate,
        branch_id,
        wan1_pa_ip,
        wan1_fg_ip,
        wan2_pa_ip,
        wan2_fg_ip,
        vpn1_pa_ip,
        vpn1_fg_ip,
        vpn2_pa_ip,
        vpn2_fg_ip,
    ):
        plan = build_paloalto_branch_plan(branch_id)

        checks = []

        def check(
            name,
            values,
        ):
            missing = [value for value in values if value not in candidate]

            checks.append(
                (
                    name,
                    not missing,
                    ", ".join(missing),
                )
            )

        check(
            "IKE Gateway VPN1",
            (
                plan.ipsec1_name,
                "IKE-FGT-PA",
                "ethernet1/1",
                wan1_pa_ip,
                wan1_fg_ip,
            ),
        )

        check(
            "IKE Gateway VPN2",
            (
                plan.ipsec2_name,
                "IKE-FGT-PA",
                "ethernet1/3",
                wan2_pa_ip,
                wan2_fg_ip,
            ),
        )

        check(
            "IPsec tunnel VPN1",
            (
                plan.ipsec1_name,
                "IPSEC-FGT-PA",
                plan.tunnel1_name,
            ),
        )

        check(
            "IPsec tunnel VPN2",
            (
                plan.ipsec2_name,
                "IPSEC-FGT-PA",
                plan.tunnel2_name,
            ),
        )

        check(
            "Tunnel interface VPN1",
            (
                plan.tunnel1_name,
                f"{vpn1_pa_ip}/30",
                "TUNNEL-MGMT",
            ),
        )

        check(
            "Tunnel interface VPN2",
            (
                plan.tunnel2_name,
                f"{vpn2_pa_ip}/30",
                "TUNNEL-MGMT",
            ),
        )

        check(
            "Security zone FILIAIS",
            (
                "set zone FILIAIS",
                plan.tunnel1_name,
                plan.tunnel2_name,
            ),
        )

        check(
            "Virtual Router default",
            (
                ("set network virtual-router default interface"),
                plan.tunnel1_name,
                plan.tunnel2_name,
            ),
        )

        check(
            "BGP peer VPN1",
            (
                "IBGP-SDWAN",
                plan.bgp_peer1_name,
                plan.tunnel1_name,
                f"{vpn1_pa_ip}/30",
                vpn1_fg_ip,
                "peer-as 65001",
            ),
        )

        check(
            "BGP peer VPN2",
            (
                "IBGP-SDWAN",
                plan.bgp_peer2_name,
                plan.tunnel2_name,
                f"{vpn2_pa_ip}/30",
                vpn2_fg_ip,
                "peer-as 65001",
            ),
        )

        # Não permitimos explosão de policies.
        policy_regression = "set rulebase security rules" in candidate

        checks.append(
            (
                "No per-branch policies",
                not policy_regression,
                (
                    "Candidate tentou criar Security Policy."
                    if policy_regression
                    else ""
                ),
            )
        )

        # Contrato de addressing:
        # PA = primeiro usable.
        checks.append(
            (
                "PA first usable",
                (f"{vpn1_pa_ip}/30" in candidate and f"{vpn2_pa_ip}/30" in candidate),
                "",
            )
        )

        checks.append(
            (
                "FG second usable",
                (vpn1_fg_ip in candidate and vpn2_fg_ip in candidate),
                "",
            )
        )

        return PaloAltoComplianceReport(checks=tuple(checks))
