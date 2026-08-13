from ipaddress import IPv4Network

from src.branch.addressing import build_branch_plan


def generate_paloalto_branch_config(
    branch_id: int,
    branch_wan1_ip: str,
    branch_wan2_ip: str,
    psk: str,
) -> str:
    plan = build_branch_plan(branch_id)

    vpn1 = IPv4Network(plan.vpn1_prefix)
    vpn2 = IPv4Network(plan.vpn2_prefix)

    vpn1_hosts = list(vpn1.hosts())
    vpn2_hosts = list(vpn2.hosts())

    tunnel1 = ((branch_id - 1) * 2) + 1
    tunnel2 = tunnel1 + 1

    return f"""
set network interface tunnel units tunnel.{tunnel1} ip {vpn1_hosts[0]}/{vpn1.prefixlen}
set network interface tunnel units tunnel.{tunnel2} ip {vpn2_hosts[0]}/{vpn2.prefixlen}

set network virtual-router default interface tunnel.{tunnel1}
set network virtual-router default interface tunnel.{tunnel2}

set zone FILIAIS network layer3 tunnel.{tunnel1}
set zone FILIAIS network layer3 tunnel.{tunnel2}

set network virtual-router default protocol bgp peer-group IBGP-SDWAN peer FG-BRANCH-{branch_id}-VPN1 peer-address ip {vpn1_hosts[1]}
set network virtual-router default protocol bgp peer-group IBGP-SDWAN peer FG-BRANCH-{branch_id}-VPN1 local-address interface tunnel.{tunnel1}
set network virtual-router default protocol bgp peer-group IBGP-SDWAN peer FG-BRANCH-{branch_id}-VPN1 peer-as 65001

set network virtual-router default protocol bgp peer-group IBGP-SDWAN peer FG-BRANCH-{branch_id}-VPN2 peer-address ip {vpn2_hosts[1]}
set network virtual-router default protocol bgp peer-group IBGP-SDWAN peer FG-BRANCH-{branch_id}-VPN2 local-address interface tunnel.{tunnel2}
set network virtual-router default protocol bgp peer-group IBGP-SDWAN peer FG-BRANCH-{branch_id}-VPN2 peer-as 65001
""".strip()
