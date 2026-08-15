from src.switch.provisioning.interface_range import (
    build_interface_groups,
)
from src.switch.provisioning.profiles import (
    BRANCH_STANDARD_V1,
)

#
# A ORDEM ABAIXO É CONTRATO DO CANDIDATE.
#
# Não simplificar.
# Não reordenar silenciosamente.
#
SECTION_ORDER = (
    "system",
    "hostname",
    "logging_buffer",
    "aaa",
    "network_services",
    "dhcp_snooping",
    "dot1x_global",
    "archive",
    "stp",
    "enable",
    "transceiver",
    "vlans",
    "management",
    "provision_port",
    "uplink",
    "user_ports",
    "radius_source_logging",
    "snmp",
    "radius",
    "lines",
    "ntp",
)


SECTION_LABELS = {
    "system": "Sistema",
    "hostname": "Hostname",
    "logging_buffer": "Logging Buffer",
    "aaa": "AAA",
    "network_services": "Clock / DNS",
    "dhcp_snooping": "DHCP Snooping",
    "dot1x_global": "802.1X Global",
    "archive": "Archive",
    "stp": "STP",
    "enable": "Enable Secret",
    "transceiver": "Transceiver",
    "vlans": "VLANs",
    "management": "Gerenciamento",
    "provision_port": "Provision Port",
    "uplink": "Uplink",
    "user_ports": "Portas de Usuário",
    "radius_source_logging": "RADIUS Source / Logging",
    "snmp": "SNMP",
    "radius": "RADIUS",
    "lines": "Console / VTY",
    "ntp": "NTP",
}


def _block(
    lines,
):
    return "\n".join(lines).rstrip() + "\n"


def render_branch_sections(
    *,
    variables,
    classification,
    profile=None,
):
    profile = profile or BRANCH_STANDARD_V1

    management_vlan = profile["management_vlan"]

    access_vlan = profile["access_vlan"]

    voice_vlan = profile["voice_vlan"]

    allowed_vlans = ",".join(str(vlan) for vlan in profile["allowed_vlans"])

    radius_group = profile["radius_group"]

    radius_servers = profile["radius_servers"]

    sections = {}

    # ======================================================
    # 01 - SERVICES
    # ======================================================

    sections["system"] = _block(
        [
            ("service timestamps debug datetime msec localtime show-timezone"),
            ("service timestamps log datetime msec localtime show-timezone"),
            "service password-encryption",
            "service compress-config",
            *(
                ["service unsupported-transceiver"]
                if profile.get(
                    "unsupported_transceiver",
                    False,
                )
                else []
            ),
            *(
                [("platform punt-keepalive disable-kernel-core")]
                if profile.get(
                    "platform_punt_keepalive",
                    False,
                )
                else []
            ),
            "!",
        ]
    )

    # ======================================================
    # 02 - HOSTNAME
    # ======================================================

    sections["hostname"] = _block(
        [
            (f"hostname {variables.hostname}"),
            "!",
        ]
    )

    # ======================================================
    # 03 - LOGGING BUFFER
    # ======================================================

    sections["logging_buffer"] = _block(
        [
            (f"logging buffered {profile['logging_buffered']}"),
            "!",
        ]
    )

    # ======================================================
    # 04 - AAA
    #
    # BLOCO MÍNIMO OBRIGATÓRIO.
    # NÃO SIMPLIFICAR.
    # ======================================================

    aaa_lines = [
        "aaa new-model",
        "!",
        "!",
        (f"aaa group server radius {radius_group}"),
    ]

    for server in radius_servers:
        aaa_lines.append((f" server name {server['name']}"))

    aaa_lines.extend(
        [
            "!",
            ("aaa authentication login default local"),
            ("aaa authentication dot1x default group RAD"),
            ("aaa authorization exec default local"),
            ("aaa authorization network default group RAD"),
            ("aaa authorization auth-proxy default group RAD"),
            ("aaa accounting update newinfo periodic 2880"),
            ("aaa accounting dot1x default start-stop group RAD"),
            ("aaa accounting system default start-stop group RAD"),
            "!",
            "!",
            ("aaa server radius dynamic-author"),
        ]
    )

    for server in radius_servers:
        aaa_lines.append(
            (f" client {server['address']} server-key 7 {server['coa_key']}")
        )

    aaa_lines.extend(
        [
            "!",
            "aaa session-id common",
            "!",
        ]
    )

    sections["aaa"] = _block(aaa_lines)

    # ======================================================
    # 05 - CLOCK / DNS
    # ======================================================

    sections["network_services"] = _block(
        [
            (f"clock timezone {profile['timezone']}"),
            "!",
            ("ip name-server " + " ".join(profile["name_servers"])),
            (f"{profile['domain_command']} {profile['domain_name']}"),
            "!",
        ]
    )

    # ======================================================
    # 06 - DHCP SNOOPING
    #
    # 1-4094 DELIBERADAMENTE.
    # ======================================================

    sections["dhcp_snooping"] = _block(
        [
            (f"ip dhcp snooping vlan {profile['dhcp_snooping_vlan_range']}"),
            ("no ip dhcp snooping information option"),
            "ip dhcp snooping",
            "!",
        ]
    )

    # ======================================================
    # 07 - DOT1X GLOBAL
    # ======================================================

    sections["dot1x_global"] = _block(
        [
            "dot1x system-auth-control",
            "!",
        ]
    )

    # ======================================================
    # 08 - ARCHIVE
    # ======================================================

    sections["archive"] = _block(
        [
            "archive",
            " log config",
            "  logging enable",
            "!",
        ]
    )

    # ======================================================
    # 09 - STP
    # ======================================================

    sections["stp"] = _block(
        [
            (f"spanning-tree mode {profile['spanning_tree_mode']}"),
            "spanning-tree portfast default",
            ("spanning-tree portfast bpduguard default"),
            "!",
        ]
    )

    # ======================================================
    # 10 - ENABLE SECRET
    # ======================================================

    sections["enable"] = _block(
        [
            (f"enable secret 9 {profile['enable_secret']}"),
            "!",
        ]
    )

    # ======================================================
    # 11 - TRANSCEIVER
    # ======================================================

    sections["transceiver"] = _block(
        [
            *(
                [
                    "transceiver type all",
                    " monitoring",
                ]
                if profile.get(
                    "transceiver_monitoring",
                    False,
                )
                else []
            ),
            "!",
        ]
    )

    # ======================================================
    # 12 - VLANS
    #
    # NÃO EXISTE VLAN 666 NESTA BASELINE.
    # ======================================================

    sections["vlans"] = _block(
        [
            (f"vlan {access_vlan}"),
            " name DATA",
            "!",
            (f"vlan {voice_vlan}"),
            " name VOICE",
            "!",
            (f"vlan {management_vlan}"),
            " name MANAGEMENT",
            "!",
        ]
    )

    # ======================================================
    # 13 - MANAGEMENT
    # ======================================================

    sections["management"] = _block(
        [
            (f"interface Vlan{management_vlan}"),
            (" description ## MANAGEMENT ##"),
            (f" ip address {variables.management_ip} {variables.management_mask}"),
            " no shutdown",
            "!",
            (f"ip default-gateway {variables.default_gateway}"),
            "!",
        ]
    )

    # ======================================================
    # 14 - PROVISION PORT
    #
    # NÃO ALTERAR:
    # IP
    # máscara
    # routed/switchport
    # shutdown
    # ======================================================

    sections["provision_port"] = _block(
        [
            (f"interface {classification.provision_port}"),
            (" description ## PORTA PARA PROVISIONAMENTO ##"),
            "!",
        ]
    )

    # ======================================================
    # 15 - UPLINK
    # ======================================================

    sections["uplink"] = _block(
        [
            (f"interface {classification.uplink}"),
            (" description ## UPLINK FIREWALL ##"),
            " switchport mode trunk",
            (f" switchport trunk allowed vlan {allowed_vlans}"),
            " switchport nonegotiate",
            " ip dhcp snooping trust",
            "!",
        ]
    )

    # ======================================================
    # 16 - USER PORTS
    #
    # Sem VLAN 666.
    # Sem IPDT.
    # Uma única authentication open.
    # ======================================================

    user_commands = [
        ("description ## PORTA-DE-USUARIO ##"),
        (f"switchport access vlan {access_vlan}"),
        "switchport mode access",
        "switchport nonegotiate",
        (f"switchport voice vlan {voice_vlan}"),
        ("authentication event fail action next-method"),
        ("authentication event server alive action reinitialize"),
        ("authentication host-mode multi-domain"),
        "authentication open",
        ("authentication order dot1x mab"),
        ("authentication priority dot1x mab"),
        ("authentication port-control auto"),
        ("authentication violation restrict"),
        "mab",
        "dot1x pae authenticator",
        "dot1x timeout tx-period 15",
        "spanning-tree portfast",
    ]

    user_blocks = []

    for group in build_interface_groups(classification.user_ports):
        lines = [group["command"]]

        lines.extend((f" {command}") for command in user_commands)

        lines.append("!")

        user_blocks.append("\n".join(lines))

    sections["user_ports"] = (
        "\n".join(user_blocks).rstrip() + "\n" if user_blocks else ""
    )

    # ======================================================
    # 17 - RADIUS SOURCE / LOGGING
    # ======================================================

    logging_lines = [
        (f"ip radius source-interface Vlan{management_vlan}"),
        "logging origin-id ip",
        (f"logging source-interface Vlan{management_vlan}"),
    ]

    for server in profile["syslog_servers"]:
        if server["port"] is None:
            logging_lines.append((f"logging host {server['address']}"))

        else:
            logging_lines.append(
                (
                    "logging host "
                    f"{server['address']} "
                    "transport udp port "
                    f"{server['port']}"
                )
            )

    logging_lines.append("!")

    sections["radius_source_logging"] = _block(logging_lines)

    # ======================================================
    # 18 - SNMP
    # ======================================================

    sections["snmp"] = _block(
        [
            (f"snmp-server community {profile['snmp_community_ro']} RO"),
            (
                "snmp-server host "
                f"{profile['snmp_host']} "
                "version 2c "
                f"{profile['snmp_community_ro']}"
            ),
            "!",
        ]
    )

    # ======================================================
    # 19 - RADIUS ATTRIBUTES / SERVERS
    # ======================================================

    radius_lines = [
        ("radius-server attribute 6 on-for-login-auth"),
        ("radius-server attribute 6 support-multiple"),
        ("radius-server attribute 8 include-in-access-req"),
        ("radius-server attribute 25 access-request include"),
        ("radius-server dead-criteria time 30 tries 3"),
        "!",
    ]

    for server in radius_servers:
        radius_lines.extend(
            [
                (f"radius server {server['name']}"),
                (
                    " address ipv4 "
                    f"{server['address']} "
                    f"auth-port "
                    f"{server['auth_port']} "
                    f"acct-port "
                    f"{server['acct_port']}"
                ),
                (f" timeout {server['timeout']}"),
                (f" retransmit {server['retransmit']}"),
                (" automate-tester username dummy ignore-acct-port probe-on"),
                (f" key 7 {server['radius_key']}"),
                "!",
            ]
        )

    sections["radius"] = _block(radius_lines)

    # ======================================================
    # 20 - CONSOLE / VTY
    #
    # Login administrativo permanece DEFAULT LOCAL.
    # ======================================================

    sections["lines"] = _block(
        [
            "line con 0",
            " stopbits 1",
            "!",
            "line vty 0 4",
            " privilege level 15",
            " length 0",
            " transport input ssh",
            "!",
            "line vty 5 15",
            " privilege level 15",
            " length 0",
            " transport input ssh",
            "!",
        ]
    )

    # ======================================================
    # 21 - NTP
    # ======================================================

    ntp_lines = [(f"ntp server {server}") for server in profile["ntp_servers"]]

    ntp_lines.extend(
        [
            "!",
            "!",
            "!",
        ]
    )

    sections["ntp"] = _block(ntp_lines)

    return sections


def render_branch_candidate(
    *,
    variables,
    classification,
    profile=None,
    enabled_sections=None,
    overrides="",
):
    sections = render_branch_sections(
        variables=variables,
        classification=classification,
        profile=profile,
    )

    if enabled_sections is None:
        enabled_sections = list(SECTION_ORDER)

    enabled_sections = set(enabled_sections)

    parts = []

    for section_name in SECTION_ORDER:
        if section_name not in enabled_sections:
            continue

        section = sections.get(
            section_name,
            "",
        )

        if section.strip():
            parts.append(section.rstrip())

    override_text = str(overrides or "").strip()

    if override_text:
        parts.extend(
            [
                "!",
                ("! ===== OVERRIDES DO OPERADOR ====="),
                override_text,
            ]
        )

    return "\n".join(parts).rstrip() + "\n"
