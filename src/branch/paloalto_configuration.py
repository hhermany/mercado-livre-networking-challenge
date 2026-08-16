from ipaddress import IPv4Network

from src.branch.addressing import (
    build_branch_plan,
)
from src.branch.paloalto_contract import (
    build_paloalto_branch_plan,
)


def generate_paloalto_branch_config(
    *,
    branch_id,
    branch_wan1_ip,
    branch_wan2_ip,
    psk,
):
    """
    Gera configuracao incremental para adicionar
    uma nova Branch ao Palo Alto do DC.

    Mantem o contrato publico historico usado
    por bundle, onboarding e Flask.
    """

    branch = build_branch_plan(branch_id)

    pa = build_paloalto_branch_plan(branch_id)

    vpn1 = IPv4Network(branch.vpn1_prefix)

    vpn2 = IPv4Network(branch.vpn2_prefix)

    vpn1_hosts = list(vpn1.hosts())

    vpn2_hosts = list(vpn2.hosts())

    # Contrato:
    # primeiro usable = PA
    # segundo usable  = FortiGate
    vpn1_pa_ip = str(vpn1_hosts[0])

    vpn1_fg_ip = str(vpn1_hosts[1])

    vpn2_pa_ip = str(vpn2_hosts[0])

    vpn2_fg_ip = str(vpn2_hosts[1])

    bgp_base = (
        "set network virtual-router default protocol bgp peer-group IBGP-SDWAN peer"
    )

    commands = [
        # ====================================================
        # IKE GATEWAY VPN1
        # ====================================================
        (
            "set network ike gateway "
            f"{pa.ipsec1_name} "
            "protocol ikev2 "
            "ike-crypto-profile IKE-FGT-PA"
        ),
        (f"set network ike gateway {pa.ipsec1_name} protocol version ikev2"),
        (
            "set network ike gateway "
            f"{pa.ipsec1_name} "
            "local-address interface ethernet1/1"
        ),
        (f"set network ike gateway {pa.ipsec1_name} local-address ip 100.64.0.1/24"),
        (f"set network ike gateway {pa.ipsec1_name} peer-address ip {branch_wan1_ip}"),
        (
            "set network ike gateway "
            f"{pa.ipsec1_name} "
            "authentication pre-shared-key "
            f'key "{psk}"'
        ),
        # ====================================================
        # IKE GATEWAY VPN2
        # ====================================================
        (
            "set network ike gateway "
            f"{pa.ipsec2_name} "
            "protocol ikev2 "
            "ike-crypto-profile IKE-FGT-PA"
        ),
        (f"set network ike gateway {pa.ipsec2_name} protocol version ikev2"),
        (
            "set network ike gateway "
            f"{pa.ipsec2_name} "
            "local-address interface ethernet1/3"
        ),
        (f"set network ike gateway {pa.ipsec2_name} local-address ip 100.100.0.1/24"),
        (f"set network ike gateway {pa.ipsec2_name} peer-address ip {branch_wan2_ip}"),
        (
            "set network ike gateway "
            f"{pa.ipsec2_name} "
            "authentication pre-shared-key "
            f'key "{psk}"'
        ),
        # ====================================================
        # TUNNEL INTERFACES
        # ====================================================
        (f"set network interface tunnel units {pa.tunnel1_name} ip {vpn1_pa_ip}/30"),
        (
            "set network interface tunnel units "
            f"{pa.tunnel1_name} "
            "interface-management-profile "
            "TUNNEL-MGMT"
        ),
        (f"set network interface tunnel units {pa.tunnel2_name} ip {vpn2_pa_ip}/30"),
        (
            "set network interface tunnel units "
            f"{pa.tunnel2_name} "
            "interface-management-profile "
            "TUNNEL-MGMT"
        ),
        # ====================================================
        # IPSEC TUNNELS
        # ====================================================
        (
            "set network tunnel ipsec "
            f"{pa.ipsec1_name} "
            "auto-key ike-gateway "
            f"{pa.ipsec1_name}"
        ),
        (
            "set network tunnel ipsec "
            f"{pa.ipsec1_name} "
            "auto-key ipsec-crypto-profile "
            "IPSEC-FGT-PA"
        ),
        (
            "set network tunnel ipsec "
            f"{pa.ipsec1_name} "
            "tunnel-interface "
            f"{pa.tunnel1_name}"
        ),
        (
            "set network tunnel ipsec "
            f"{pa.ipsec2_name} "
            "auto-key ike-gateway "
            f"{pa.ipsec2_name}"
        ),
        (
            "set network tunnel ipsec "
            f"{pa.ipsec2_name} "
            "auto-key ipsec-crypto-profile "
            "IPSEC-FGT-PA"
        ),
        (
            "set network tunnel ipsec "
            f"{pa.ipsec2_name} "
            "tunnel-interface "
            f"{pa.tunnel2_name}"
        ),
        # ====================================================
        # ZONE COMPARTILHADA
        #
        # Policies existentes:
        # FILIAIS-TO-DC
        # DC-TO-FILIAIS
        # ====================================================
        (f"set zone FILIAIS network layer3 {pa.tunnel1_name}"),
        (f"set zone FILIAIS network layer3 {pa.tunnel2_name}"),
        # ====================================================
        # VIRTUAL ROUTER
        # ====================================================
        (f"set network virtual-router default interface {pa.tunnel1_name}"),
        (f"set network virtual-router default interface {pa.tunnel2_name}"),
        # ====================================================
        # BGP VPN1
        # ====================================================
        (f"{bgp_base} {pa.bgp_peer1_name} peer-address ip {vpn1_fg_ip}"),
        (f"{bgp_base} {pa.bgp_peer1_name} local-address interface {pa.tunnel1_name}"),
        (f"{bgp_base} {pa.bgp_peer1_name} local-address ip {vpn1_pa_ip}/30"),
        (f"{bgp_base} {pa.bgp_peer1_name} peer-as 65001"),
        # ====================================================
        # BGP VPN2
        # ====================================================
        (f"{bgp_base} {pa.bgp_peer2_name} peer-address ip {vpn2_fg_ip}"),
        (f"{bgp_base} {pa.bgp_peer2_name} local-address interface {pa.tunnel2_name}"),
        (f"{bgp_base} {pa.bgp_peer2_name} local-address ip {vpn2_pa_ip}/30"),
        (f"{bgp_base} {pa.bgp_peer2_name} peer-as 65001"),
    ]

    return "\n".join(commands)
