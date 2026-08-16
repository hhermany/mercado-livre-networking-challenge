import pytest

import src.branch.provisioning as provisioning


def build_provisioner():
    return provisioning.BranchProvisioner.__new__(provisioning.BranchProvisioner)


def test_plan_uses_next_branch_without_writing(
    monkeypatch,
):
    monkeypatch.setattr(
        provisioning,
        "get_next_branch_id",
        lambda: 4,
    )

    provisioner = build_provisioner()

    def forbidden_create(
        *args,
        **kwargs,
    ):
        raise AssertionError("plan() must not write to Nautobot")

    monkeypatch.setattr(
        provisioner,
        "_create_prefix",
        forbidden_create,
    )

    plan = provisioner.plan()

    assert plan.branch_id == 4
    assert plan.name == "BRANCH-4"

    assert plan.lan_prefix == "10.0.3.0/24"

    assert plan.loopback_prefix == "172.31.255.4/32"

    assert plan.vpn1_prefix == "169.255.0.16/30"

    assert plan.vpn2_prefix == "169.255.0.20/30"


def test_plan_can_rebuild_exact_candidate():
    provisioner = build_provisioner()

    plan = provisioner.plan(branch_id=7)

    assert plan.branch_id == 7
    assert plan.name == "BRANCH-7"

    assert plan.lan_prefix == "10.0.6.0/24"

    assert plan.loopback_prefix == "172.31.255.7/32"

    assert plan.vpn1_prefix == "169.255.0.40/30"

    assert plan.vpn2_prefix == "169.255.0.44/30"


def test_provision_reserves_exact_candidate_plan(
    monkeypatch,
):
    provisioner = build_provisioner()

    provisioner.base = "http://nautobot"

    provisioner.headers = {}

    created = []

    def fake_create(
        prefix,
        description,
    ):
        created.append(
            (
                prefix,
                description,
            )
        )

        return {
            "id": prefix,
            "prefix": prefix,
        }

    monkeypatch.setattr(
        provisioner,
        "_create_prefix",
        fake_create,
    )

    monkeypatch.setattr(
        provisioner,
        "_create_overlay_inventory",
        lambda plan, tunnel_number, prefix: {
            "ip_addresses": [],
            "vpns": [],
            "vpn_endpoints": [],
            "vpn_tunnels": [],
        },
    )

    plan = provisioner.provision(branch_id=5)

    assert plan.branch_id == 5

    assert created == [
        (
            "10.0.4.0/24",
            "BRANCH-5 LAN",
        ),
        (
            "172.31.255.5/32",
            "BRANCH-5 LO-MGMT",
        ),
        (
            "169.255.0.24/30",
            "BRANCH-5 VPN1",
        ),
        (
            "169.255.0.28/30",
            "BRANCH-5 VPN2",
        ),
    ]


def test_provision_rolls_back_partial_reservation(
    monkeypatch,
):
    provisioner = build_provisioner()

    provisioner.base = "http://nautobot"

    provisioner.headers = {}

    counter = {
        "value": 0,
    }

    def fake_create(
        prefix,
        description,
    ):
        counter["value"] += 1

        if counter["value"] == 3:
            raise RuntimeError("simulated Nautobot failure")

        return {
            "id": f"id-{counter['value']}",
            "prefix": prefix,
        }

    deleted = []

    class FakeDeleteResponse:
        def raise_for_status(self):
            return None

    def fake_delete(
        url,
        **kwargs,
    ):
        deleted.append(url)

        return FakeDeleteResponse()

    monkeypatch.setattr(
        provisioner,
        "_create_prefix",
        fake_create,
    )

    monkeypatch.setattr(
        provisioning.requests,
        "delete",
        fake_delete,
    )

    with pytest.raises(
        RuntimeError,
        match="simulated",
    ):
        provisioner.provision(branch_id=6)

    assert deleted == [
        ("http://nautobot/api/ipam/prefixes/id-2/"),
        ("http://nautobot/api/ipam/prefixes/id-1/"),
    ]
