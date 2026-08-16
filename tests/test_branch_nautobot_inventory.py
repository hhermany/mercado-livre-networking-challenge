from src.branch.addressing import (
    build_branch_plan,
)
from src.branch.provisioning import (
    BranchProvisioner,
)


def build_provisioner():
    return BranchProvisioner.__new__(BranchProvisioner)


def test_overlay_hosts_follow_pa_fg_contract():
    provisioner = build_provisioner()

    pa, fg = provisioner._overlay_hosts("169.255.0.0/30")

    assert pa == "169.255.0.1"
    assert fg == "169.255.0.2"


def test_branch2_overlay_inventory_addresses(
    monkeypatch,
):
    provisioner = build_provisioner()
    plan = build_branch_plan(2)

    created_ips = []

    monkeypatch.setattr(
        provisioner,
        "_create_ip_address",
        lambda address, description: (
            created_ips.append((address, description))
            or {
                "id": address,
                "address": address,
            }
        ),
    )

    monkeypatch.setattr(
        provisioner,
        "_create_vpn",
        lambda name, description: {
            "id": name,
            "name": name,
        },
    )

    endpoint_counter = {
        "value": 0,
    }

    def endpoint(**kwargs):
        endpoint_counter["value"] += 1
        return {
            "id": (f"endpoint-{endpoint_counter['value']}"),
        }

    monkeypatch.setattr(
        provisioner,
        "_create_vpn_endpoint",
        endpoint,
    )

    monkeypatch.setattr(
        provisioner,
        "_create_vpn_tunnel",
        lambda **kwargs: {
            "id": kwargs["name"],
            "name": kwargs["name"],
        },
    )

    provisioner._create_overlay_inventory(
        plan,
        1,
        plan.vpn1_prefix,
    )

    provisioner._create_overlay_inventory(
        plan,
        2,
        plan.vpn2_prefix,
    )

    assert created_ips == [
        (
            "169.255.0.1/30",
            ("BRANCH-2 VPN1 Palo Alto DC endpoint"),
        ),
        (
            "169.255.0.2/30",
            ("BRANCH-2 VPN1 FortiGate branch endpoint"),
        ),
        (
            "169.255.0.5/30",
            ("BRANCH-2 VPN2 Palo Alto DC endpoint"),
        ),
        (
            "169.255.0.6/30",
            ("BRANCH-2 VPN2 FortiGate branch endpoint"),
        ),
    ]


def test_overlay_inventory_builds_vpn_relationships(
    monkeypatch,
):
    provisioner = build_provisioner()
    plan = build_branch_plan(2)

    monkeypatch.setattr(
        provisioner,
        "_create_ip_address",
        lambda address, description: {
            "id": address,
            "address": address,
        },
    )

    monkeypatch.setattr(
        provisioner,
        "_create_vpn",
        lambda name, description: {
            "id": "vpn-id",
            "name": name,
        },
    )

    endpoint_ids = iter(
        (
            "pa-endpoint",
            "fg-endpoint",
        )
    )

    monkeypatch.setattr(
        provisioner,
        "_create_vpn_endpoint",
        lambda **kwargs: {
            "id": next(endpoint_ids),
        },
    )

    tunnel_payload = {}

    def create_tunnel(**kwargs):
        tunnel_payload.update(kwargs)

        return {
            "id": "tunnel-id",
        }

    monkeypatch.setattr(
        provisioner,
        "_create_vpn_tunnel",
        create_tunnel,
    )

    provisioner._create_overlay_inventory(
        plan,
        1,
        plan.vpn1_prefix,
    )

    assert tunnel_payload == {
        "name": "BRANCH-2-VPN1",
        "description": ("VPN 1 with BRANCH-2"),
        "vpn_id": "vpn-id",
        "endpoint_a": "pa-endpoint",
        "endpoint_z": "fg-endpoint",
    }


def test_release_full_inventory_reverse_dependency(
    monkeypatch,
):
    provisioner = build_provisioner()

    deleted = []

    monkeypatch.setattr(
        provisioner,
        "_delete",
        lambda path, object_id: deleted.append((path, object_id)),
    )

    provisioner.release(
        {
            "prefixes": [{"id": "prefix"}],
            "ip_addresses": [{"id": "ip"}],
            "vpns": [{"id": "vpn"}],
            "vpn_endpoints": [{"id": "endpoint"}],
            "vpn_tunnels": [{"id": "tunnel"}],
        }
    )

    assert deleted == [
        (
            "/api/vpn/vpn-tunnels/",
            "tunnel",
        ),
        (
            "/api/vpn/vpn-tunnel-endpoints/",
            "endpoint",
        ),
        (
            "/api/vpn/vpns/",
            "vpn",
        ),
        (
            "/api/ipam/ip-addresses/",
            "ip",
        ),
        (
            "/api/ipam/prefixes/",
            "prefix",
        ),
    ]
