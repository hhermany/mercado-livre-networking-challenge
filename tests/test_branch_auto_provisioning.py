import src.branch.provisioning as provisioning


def test_provision_uses_next_branch_id(
    monkeypatch,
):
    monkeypatch.setattr(
        provisioning,
        "get_next_branch_id",
        lambda: 3,
    )

    monkeypatch.setattr(
        provisioning.BranchProvisioner,
        "_create_prefix",
        lambda self, prefix, description: {
            "id": prefix,
            "prefix": prefix,
        },
    )

    monkeypatch.setattr(
        provisioning.BranchProvisioner,
        "_create_overlay_inventory",
        lambda self, plan, tunnel_number, prefix: {
            "ip_addresses": [],
            "vpns": [],
            "vpn_endpoints": [],
            "vpn_tunnels": [],
        },
    )

    provisioner = provisioning.BranchProvisioner.__new__(provisioning.BranchProvisioner)

    plan = provisioner.provision()

    assert plan.branch_id == 3
    assert plan.name == "BRANCH-3"

    assert plan.hostname == "FW-BRANCH-3"

    assert plan.lan_prefix == "10.0.2.0/24"

    assert plan.loopback_prefix == "172.31.255.3/32"

    assert plan.vpn1_prefix == "169.255.0.8/30"

    assert plan.vpn2_prefix == "169.255.0.12/30"
