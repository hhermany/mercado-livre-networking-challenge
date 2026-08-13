import src.branch.provisioning as provisioning


def test_provision_uses_next_branch_id(monkeypatch):
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

    provisioner = provisioning.BranchProvisioner.__new__(
        provisioning.BranchProvisioner
    )

    plan = provisioner.provision()

    assert plan.branch_id == 3
    assert plan.name == "BRANCH-3"
    assert plan.hostname == "FW-BRANCH-3"
    assert plan.lan_prefix == "10.0.2.0/24"
    assert plan.loopback_prefix == "172.31.255.3/32"
    assert plan.vpn1_prefix == "169.255.3.0/30"
    assert plan.vpn2_prefix == "169.255.3.4/30"
