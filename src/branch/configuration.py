from ipaddress import IPv4Interface, IPv4Network

from src.branch.addressing import build_branch_plan
from src.branch.models import (
    BranchWANInput,
    IPsecPhase1Input,
    IPsecPhase2Input,
)
from src.templates.renderer import TemplateRenderer


def generate_fortigate_branch_config(
    branch_id: int,
    wan: BranchWANInput,
    phase1: IPsecPhase1Input,
    phase2: IPsecPhase2Input,
    dc_wan1_ip: str,
    dc_wan2_ip: str,
    hostname: str | None = None,
) -> str:
    plan = build_branch_plan(branch_id)

    lan = IPv4Network(plan.lan_prefix)
    vpn1 = IPv4Network(plan.vpn1_prefix)
    vpn2 = IPv4Network(plan.vpn2_prefix)

    wan1 = IPv4Interface(wan.wan1_ip)
    wan2 = IPv4Interface(wan.wan2_ip)

    lan_hosts = list(lan.hosts())
    vpn1_hosts = list(vpn1.hosts())
    vpn2_hosts = list(vpn2.hosts())

    renderer = TemplateRenderer()

    return renderer.render(
        "fortigate/branch_full.j2",
        {
            "name": plan.name,
            "hostname": hostname or plan.hostname,
            "lan_network": str(lan.network_address),
            "lan_gateway": str(lan_hosts[-1]),
            "dhcp_start": str(lan_hosts[0]),
            "dhcp_end": str(lan_hosts[9]),
            "loopback_ip": plan.loopback_prefix.split("/")[0],
            "wan1_ip": str(wan1.ip),
            "wan1_mask": str(wan1.netmask),
            "wan1_gateway": wan.wan1_gateway,
            "wan2_ip": str(wan2.ip),
            "wan2_mask": str(wan2.netmask),
            "wan2_gateway": wan.wan2_gateway,
            "vpn1_dc_ip": str(vpn1_hosts[0]),
            "vpn1_branch_ip": str(vpn1_hosts[1]),
            "vpn2_dc_ip": str(vpn2_hosts[0]),
            "vpn2_branch_ip": str(vpn2_hosts[1]),
            "dc_wan1_ip": dc_wan1_ip,
            "dc_wan2_ip": dc_wan2_ip,
            "phase1_ike_version": phase1.ike_version,
            "phase1_proposal": phase1.proposal,
            "phase1_dh_group": phase1.dh_group,
            "phase1_psk": phase1.psk,
            "phase2_proposal": phase2.proposal,
            "phase2_dh_group": phase2.dh_group,
        },
    )
