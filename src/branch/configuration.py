from ipaddress import IPv4Network

from src.branch.addressing import build_branch_plan
from src.templates.renderer import TemplateRenderer


def generate_fortigate_branch_config(
    branch_id: int,
    psk: str,
    dc_wan1_ip: str,
    dc_wan2_ip: str,
) -> str:
    plan = build_branch_plan(branch_id)

    lan = IPv4Network(plan.lan_prefix)
    vpn1 = IPv4Network(plan.vpn1_prefix)
    vpn2 = IPv4Network(plan.vpn2_prefix)

    lan_hosts = list(lan.hosts())
    vpn1_hosts = list(vpn1.hosts())
    vpn2_hosts = list(vpn2.hosts())

    renderer = TemplateRenderer()

    return renderer.render(
        "fortigate/branch_full.j2",
        {
            "name": plan.name,
            "hostname": plan.hostname,
            "lan_network": str(lan.network_address),
            "lan_gateway": str(lan_hosts[-1]),
            "loopback_ip": plan.loopback_prefix.split("/")[0],
            "vpn1_dc_ip": str(vpn1_hosts[0]),
            "vpn1_branch_ip": str(vpn1_hosts[1]),
            "vpn2_dc_ip": str(vpn2_hosts[0]),
            "vpn2_branch_ip": str(vpn2_hosts[1]),
            "dc_wan1_ip": dc_wan1_ip,
            "dc_wan2_ip": dc_wan2_ip,
            "psk": psk,
        },
    )
