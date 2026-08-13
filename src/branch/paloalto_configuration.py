from ipaddress import IPv4Network

from src.branch.addressing import build_branch_plan
from src.templates.renderer import TemplateRenderer


def generate_paloalto_branch_config(
    branch_id: int,
    branch_wan1_ip: str,
    branch_wan2_ip: str,
    psk: str,
) -> str:
    plan = build_branch_plan(branch_id)
    renderer = TemplateRenderer()

    vpn1 = IPv4Network(plan.vpn1_prefix)
    vpn2 = IPv4Network(plan.vpn2_prefix)

    vpn1_hosts = list(vpn1.hosts())
    vpn2_hosts = list(vpn2.hosts())

    tunnel1 = ((branch_id - 1) * 2) + 1
    tunnel2 = tunnel1 + 1

    tunnel1_name = f"{plan.name}-VPN1"
    tunnel2_name = f"{plan.name}-VPN2"

    ipsec1 = renderer.render(
        "paloalto/ipsec_tunnel.j2",
        {
            "tunnel_name": tunnel1_name,
            "wan_interface": "ethernet1/1",
            "remote_public_ip": branch_wan1_ip,
            "psk": psk,
            "tunnel_interface": f"tunnel.{tunnel1}",
        },
    )

    ipsec2 = renderer.render(
        "paloalto/ipsec_tunnel.j2",
        {
            "tunnel_name": tunnel2_name,
            "wan_interface": "ethernet1/3",
            "remote_public_ip": branch_wan2_ip,
            "psk": psk,
            "tunnel_interface": f"tunnel.{tunnel2}",
        },
    )

    peer1 = f"FG-BRANCH-{branch_id}-VPN1"
    peer2 = f"FG-BRANCH-{branch_id}-VPN2"

    bgp_base = "set network virtual-router default protocol bgp"
    bgp_peer = f"{bgp_base} peer-group IBGP-SDWAN peer"

    overlay_commands = [
        (
            f"set network interface tunnel units tunnel.{tunnel1} "
            f"ip {vpn1_hosts[0]}/{vpn1.prefixlen}"
        ),
        (
            f"set network interface tunnel units tunnel.{tunnel2} "
            f"ip {vpn2_hosts[0]}/{vpn2.prefixlen}"
        ),
        f"set network virtual-router default interface tunnel.{tunnel1}",
        f"set network virtual-router default interface tunnel.{tunnel2}",
        f"set zone FILIAIS network layer3 tunnel.{tunnel1}",
        f"set zone FILIAIS network layer3 tunnel.{tunnel2}",
        f"{bgp_peer} {peer1} peer-address ip {vpn1_hosts[1]}",
        (
            f"{bgp_peer} {peer1} local-address "
            f"interface tunnel.{tunnel1}"
        ),
        f"{bgp_peer} {peer1} peer-as 65001",
        f"{bgp_peer} {peer2} peer-address ip {vpn2_hosts[1]}",
        (
            f"{bgp_peer} {peer2} local-address "
            f"interface tunnel.{tunnel2}"
        ),
        f"{bgp_peer} {peer2} peer-as 65001",
    ]

    return "\n\n".join(
        [
            ipsec1.strip(),
            ipsec2.strip(),
            "\n".join(overlay_commands),
        ]
    )
