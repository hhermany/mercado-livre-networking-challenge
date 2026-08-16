from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ComplianceCheck:
    name: str
    success: bool
    detail: str = ""


@dataclass(frozen=True)
class GoldenComplianceReport:
    checks: tuple[ComplianceCheck, ...]

    @property
    def success(self):
        return all(check.success for check in self.checks)

    @property
    def failures(self):
        return tuple(check for check in self.checks if not check.success)

    def render(self):
        lines = [
            "FORTIGATE GOLDEN COMPLIANCE",
            "",
        ]

        for check in self.checks:
            status = "OK" if check.success else "FALHOU"

            lines.append(f"{check.name:<28} {status}")

            if not check.success and check.detail:
                lines.append(f"  -> {check.detail}")

        lines.extend(
            [
                "",
                (f"Unexpected differences: {len(self.failures)}"),
                "",
                ("COMPLIANCE: " + ("VERDE" if self.success else "VERMELHO")),
            ]
        )

        return "\n".join(lines)


class FortiGateGoldenCompliance:
    """
    Compara um Candidate parametrizado contra
    os elementos funcionais da golden real.

    Diferencas deliberadamente aceitas:
      - hostname;
      - LAN da filial;
      - loopback;
      - WAN IPs;
      - IPs dos /30;
      - PSK;
      - UUID;
      - snmp-index;
      - VPN-PA-DC da golden real ->
        VPN1-PA-DC no padrao novo.
    """

    def __init__(
        self,
        golden_dir="golden",
    ):
        self.golden_dir = Path(golden_dir)

    def _golden(self, filename):
        path = self.golden_dir / filename

        if not path.exists():
            raise FileNotFoundError(f"Snapshot golden ausente: {path}")

        return path.read_text()

    @staticmethod
    def _contains_all(
        text,
        values,
    ):
        missing = [value for value in values if value not in text]

        return (
            not missing,
            missing,
        )

    @staticmethod
    def _check(
        name,
        condition,
        detail="",
    ):
        return ComplianceCheck(
            name=name,
            success=bool(condition),
            detail=detail,
        )

    @staticmethod
    def _edit_block(
        text,
        name,
    ):
        marker = f'edit "{name}"'

        start = text.find(marker)

        if start == -1:
            return ""

        end = text.find(
            "\n    next",
            start,
        )

        if end == -1:
            return text[start:]

        return text[start:end]

    @staticmethod
    def _config_section_with_edit(
        text,
        config_name,
        edit_name,
    ):
        config_marker = f"config {config_name}"

        edit_marker = f'edit "{edit_name}"'

        position = 0

        while True:
            start = text.find(
                config_marker,
                position,
            )

            if start == -1:
                return ""

            next_config = text.find(
                "\nconfig ",
                start + len(config_marker),
            )

            if next_config == -1:
                section = text[start:]
            else:
                section = text[start:next_config]

            if edit_marker in section:
                return section

            if next_config == -1:
                return ""

            position = next_config + 1

    def evaluate(
        self,
        *,
        candidate,
        branch_id,
        hostname,
        lan_network,
        lan_gateway,
        loopback_ip,
        wan1_ip,
        wan2_ip,
        vpn1_pa_ip,
        vpn1_fg_ip,
        vpn2_pa_ip,
        vpn2_fg_ip,
    ):
        checks = []

        interfaces_golden = self._golden("system_interface.conf")

        sdwan_golden = self._golden("system_sdwan.conf")

        bgp_golden = self._golden("router_bgp.conf")

        phase1_golden = self._golden("ipsec_phase1.conf")

        phase2_golden = self._golden("ipsec_phase2.conf")

        route_map_golden = self._golden("router_route_map.conf")

        community_golden = self._golden("router_community_list.conf")

        policies_golden = self._golden("firewall_policy.conf")

        addresses_golden = self._golden("firewall_address.conf")

        services_golden = self._golden("service_group.conf")

        static_golden = self._golden("router_static.conf")

        # ----------------------------------------------------
        # SYSTEM GLOBAL
        # ----------------------------------------------------

        checks.append(
            self._check(
                "System global",
                (f'set hostname "{hostname}"' in candidate),
                ("Hostname parametrizado nao encontrado."),
            )
        )

        # ----------------------------------------------------
        # PHYSICAL INTERFACES
        # ----------------------------------------------------

        golden_ok, _ = self._contains_all(
            interfaces_golden,
            (
                'edit "port2"',
                'edit "port3"',
                'edit "port4"',
                "set allowaccess ping",
                'set vdom "root"',
            ),
        )

        candidate_ok, missing = self._contains_all(
            candidate,
            (
                'edit "port2"',
                'edit "port3"',
                'edit "port4"',
                (f"set ip {wan1_ip} 255.255.255.0"),
                (f"set ip {wan2_ip} 255.255.255.0"),
                (f"set ip {lan_gateway} 255.255.255.0"),
                ("set allowaccess ping https http"),
            ),
        )

        checks.append(
            self._check(
                "Physical interfaces",
                golden_ok and candidate_ok,
                ", ".join(missing),
            )
        )

        # ----------------------------------------------------
        # LOOPBACK
        # ----------------------------------------------------

        candidate_ok, missing = self._contains_all(
            candidate,
            (
                'edit "LO-MGMT"',
                (f"set ip {loopback_ip} 255.255.255.255"),
                "set type loopback",
                ("set allowaccess ping https ssh snmp http"),
            ),
        )

        checks.append(
            self._check(
                "Loopback management",
                candidate_ok,
                ", ".join(missing),
            )
        )

        # ----------------------------------------------------
        # VPN INTERFACES
        #
        # VPN1/VPN2 aparecem em varios contextos.
        # Estes atributos pertencem especificamente
        # a "config system interface".
        # ----------------------------------------------------

        golden_interface_section = self._config_section_with_edit(
            interfaces_golden,
            "system interface",
            "VPN-PA-DC",
        )

        candidate_interface_section = self._config_section_with_edit(
            candidate,
            "system interface",
            "VPN1-PA-DC",
        )

        golden_vpn1 = self._edit_block(
            golden_interface_section,
            "VPN-PA-DC",
        )

        golden_vpn2 = self._edit_block(
            golden_interface_section,
            "VPN2-PA-DC",
        )

        candidate_vpn1 = self._edit_block(
            candidate_interface_section,
            "VPN1-PA-DC",
        )

        candidate_vpn2 = self._edit_block(
            candidate_interface_section,
            "VPN2-PA-DC",
        )

        golden_vpn1_ok, golden_vpn1_missing = self._contains_all(
            golden_vpn1,
            (
                'set vdom "root"',
                "set allowaccess ping https",
                "set type tunnel",
                "set remote-ip",
                'set interface "port2"',
            ),
        )

        golden_vpn2_ok, golden_vpn2_missing = self._contains_all(
            golden_vpn2,
            (
                'set vdom "root"',
                "set allowaccess ping https",
                "set type tunnel",
                "set remote-ip",
                'set interface "port3"',
            ),
        )

        candidate_vpn1_ok, candidate_vpn1_missing = self._contains_all(
            candidate_vpn1,
            (
                'set vdom "root"',
                (f"set ip {vpn1_fg_ip} 255.255.255.255"),
                "set allowaccess ping https",
                "set type tunnel",
                (f"set remote-ip {vpn1_pa_ip} 255.255.255.252"),
                'set interface "port2"',
            ),
        )

        candidate_vpn2_ok, candidate_vpn2_missing = self._contains_all(
            candidate_vpn2,
            (
                'set vdom "root"',
                (f"set ip {vpn2_fg_ip} 255.255.255.255"),
                "set allowaccess ping https",
                "set type tunnel",
                (f"set remote-ip {vpn2_pa_ip} 255.255.255.252"),
                'set interface "port3"',
            ),
        )

        missing = []

        for label, values in (
            (
                "golden VPN1",
                golden_vpn1_missing,
            ),
            (
                "golden VPN2",
                golden_vpn2_missing,
            ),
            (
                "candidate VPN1",
                candidate_vpn1_missing,
            ),
            (
                "candidate VPN2",
                candidate_vpn2_missing,
            ),
        ):
            missing.extend(f"{label}: {value}" for value in values)

        checks.append(
            self._check(
                "VPN interfaces",
                (
                    golden_vpn1_ok
                    and golden_vpn2_ok
                    and candidate_vpn1_ok
                    and candidate_vpn2_ok
                ),
                ", ".join(missing),
            )
        )

        # ----------------------------------------------------
        # IPSEC PHASE1
        # ----------------------------------------------------

        golden_ok, _ = self._contains_all(
            phase1_golden,
            (
                "set ike-version 2",
                "set keylife 28800",
                "set peertype any",
                "set net-device disable",
                "set proposal des-sha256",
                "set dhgrp 14",
            ),
        )

        candidate_ok, missing = self._contains_all(
            candidate,
            (
                'edit "VPN1-PA-DC"',
                'edit "VPN2-PA-DC"',
                "set ike-version 2",
                "set keylife 28800",
                "set peertype any",
                "set net-device disable",
                "set proposal des-sha256",
                "set dhgrp 14",
            ),
        )

        checks.append(
            self._check(
                "IPsec Phase1",
                golden_ok and candidate_ok,
                ", ".join(missing),
            )
        )

        # ----------------------------------------------------
        # IPSEC PHASE2
        # ----------------------------------------------------

        golden_ok, _ = self._contains_all(
            phase2_golden,
            (
                "set proposal des-sha256",
                "set dhgrp 14",
                "set keylifeseconds 3600",
            ),
        )

        candidate_ok, missing = self._contains_all(
            candidate,
            (
                ('set phase1name "VPN1-PA-DC"'),
                ('set phase1name "VPN2-PA-DC"'),
                "set proposal des-sha256",
                "set dhgrp 14",
                "set keylifeseconds 3600",
            ),
        )

        checks.append(
            self._check(
                "IPsec Phase2",
                golden_ok and candidate_ok,
                ", ".join(missing),
            )
        )

        # ----------------------------------------------------
        # ROUTE MAPS
        # ----------------------------------------------------

        route_maps = (
            "RM-OUT-VPN1",
            "RM-OUT-VPN1-PREF",
            "RM-OUT-VPN2",
            "RM-OUT-VPN2-PREF",
        )

        golden_ok = all(f'edit "{name}"' in route_map_golden for name in route_maps)

        candidate_ok = all(f'edit "{name}"' in candidate for name in route_maps)

        checks.append(
            self._check(
                "Route maps",
                golden_ok and candidate_ok,
            )
        )

        # ----------------------------------------------------
        # COMMUNITY LISTS
        # ----------------------------------------------------

        communities = (
            "COMM-VPN1-PREFER",
            "COMM-VPN2-PREFER",
            "COMM-VPN1-DEGRADED",
            "COMM-VPN2-DEGRADED",
        )

        golden_ok = all(f'edit "{name}"' in community_golden for name in communities)

        candidate_ok = all(f'edit "{name}"' in candidate for name in communities)

        checks.append(
            self._check(
                "Community lists",
                golden_ok and candidate_ok,
            )
        )

        # ----------------------------------------------------
        # BGP
        # ----------------------------------------------------

        golden_ok, _ = self._contains_all(
            bgp_golden,
            (
                "set as 65001",
                "set ibgp-multipath enable",
                "set advertisement-interval 1",
            ),
        )

        candidate_ok, missing = self._contains_all(
            candidate,
            (
                "set as 65001",
                (f"set router-id {lan_gateway}"),
                "set ibgp-multipath enable",
                (f'edit "{vpn1_pa_ip}"'),
                (f'edit "{vpn2_pa_ip}"'),
                "set advertisement-interval 1",
                (f"set prefix {lan_network} 255.255.255.0"),
                (f"set prefix {loopback_ip} 255.255.255.255"),
            ),
        )

        checks.append(
            self._check(
                "BGP",
                golden_ok and candidate_ok,
                ", ".join(missing),
            )
        )

        # ----------------------------------------------------
        # SD-WAN
        # ----------------------------------------------------

        golden_ok, _ = self._contains_all(
            sdwan_golden,
            (
                'edit "VPN-DC"',
                'set interface "VPN-PA-DC"',
                'set interface "VPN2-PA-DC"',
                'edit "SLA_DC"',
                'set name "TO-DC"',
                "set priority-members 1 2",
                "set tie-break cfg-order",
            ),
        )

        candidate_ok, missing = self._contains_all(
            candidate,
            (
                'edit "VPN-DC"',
                ('set interface "VPN1-PA-DC"'),
                ('set interface "VPN2-PA-DC"'),
                'edit "SLA_DC"',
                ('set server "10.255.255.1"'),
                (f'edit "{vpn1_pa_ip}"'),
                (f'edit "{vpn2_pa_ip}"'),
                'set name "TO-DC"',
                "set priority-members 1 2",
                "set tie-break cfg-order",
            ),
        )

        checks.append(
            self._check(
                "SD-WAN overlay",
                golden_ok and candidate_ok,
                ", ".join(missing),
            )
        )

        # ----------------------------------------------------
        # UNDERLAY / STATIC
        # ----------------------------------------------------

        golden_static_empty = "set gateway" not in static_golden

        candidate_static_empty = (
            "config router static" not in candidate
            or "set gateway" not in candidate[candidate.find("config router static") :]
        )

        checks.append(
            self._check(
                "Static routing",
                golden_static_empty and candidate_static_empty,
                ("Golden atual nao possui static default."),
            )
        )

        # ----------------------------------------------------
        # FIREWALL ADDRESSES
        # ----------------------------------------------------

        golden_ok, _ = self._contains_all(
            addresses_golden,
            (
                'edit "BRANCH-LAN"',
                'edit "DC-LAN"',
                'edit "DC-SERVER-1"',
            ),
        )

        candidate_ok, missing = self._contains_all(
            candidate,
            (
                'edit "BRANCH-LAN"',
                (f"set subnet {lan_network} 255.255.255.0"),
                'edit "DC-LAN"',
                ("set subnet 10.255.255.0 255.255.255.0"),
                'edit "DC-SERVER-1"',
                ("set subnet 10.255.255.1 255.255.255.255"),
            ),
        )

        checks.append(
            self._check(
                "Firewall addresses",
                golden_ok and candidate_ok,
                ", ".join(missing),
            )
        )

        # ----------------------------------------------------
        # SERVICE GROUPS
        # ----------------------------------------------------

        service_groups = (
            "SERVICES-DC",
            "SERVICES-MGMT",
        )

        golden_ok = all(f'edit "{name}"' in services_golden for name in service_groups)

        candidate_ok = all(f'edit "{name}"' in candidate for name in service_groups)

        checks.append(
            self._check(
                "Service groups",
                golden_ok and candidate_ok,
            )
        )

        # ----------------------------------------------------
        # POLICIES
        # ----------------------------------------------------

        policies = (
            "BRANCH-LAN-to-VPN-DC",
            "VPN-DC-to-BRANCH-LAN",
            "DC-to-FG-MGMT",
        )

        golden_ok = all(f'set name "{name}"' in policies_golden for name in policies)

        candidate_ok = all(f'set name "{name}"' in candidate for name in policies)

        checks.append(
            self._check(
                "Firewall policies",
                golden_ok and candidate_ok,
            )
        )

        # ----------------------------------------------------
        # PROTECOES CONTRA REGRESSAO
        # ----------------------------------------------------

        checks.append(
            self._check(
                "Legacy VPN name removed",
                '"VPN-PA-DC"' not in candidate,
                ("Nome antigo VPN-PA-DC voltou ao Candidate."),
            )
        )

        checks.append(
            self._check(
                "Underlay outside SD-WAN",
                (
                    'set interface "port2"' not in self._sdwan_members(candidate)
                    and 'set interface "port3"' not in self._sdwan_members(candidate)
                ),
                ("port2/port3 apareceram como membros SD-WAN."),
            )
        )

        checks.append(
            self._check(
                "Branch identity",
                (f"BRANCH-{branch_id}" in candidate),
            )
        )

        return GoldenComplianceReport(checks=tuple(checks))

    @staticmethod
    def _sdwan_members(
        candidate,
    ):
        try:
            sdwan_start = candidate.index("config system sdwan")

            members_start = candidate.index(
                "config members",
                sdwan_start,
            )

            members_end = candidate.index(
                "\n    end",
                members_start,
            )

        except ValueError:
            return ""

        return candidate[members_start:members_end]
