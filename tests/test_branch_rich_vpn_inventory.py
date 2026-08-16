from src.branch.addressing import (
    build_branch_plan,
)
from src.branch.provisioning import (
    BranchProvisioner,
)


def provisioner():
    return BranchProvisioner.__new__(BranchProvisioner)


def reservation():
    plan = build_branch_plan(2)

    return {
        "plan": plan,
        "created": True,
        "objects": {
            "prefixes": [],
            "ip_addresses": [],
            "vpns": [
                {
                    "id": "vpn1",
                    "name": "BRANCH-2-VPN1",
                },
                {
                    "id": "vpn2",
                    "name": "BRANCH-2-VPN2",
                },
            ],
            "vpn_endpoints": [
                {"id": "e1"},
                {"id": "e2"},
                {"id": "e3"},
                {"id": "e4"},
            ],
            "vpn_tunnels": [
                {
                    "id": "t1",
                    "name": "BRANCH-2-VPN1",
                },
                {
                    "id": "t2",
                    "name": "BRANCH-2-VPN2",
                },
            ],
        },
    }


def test_rich_inventory_creates_crypto_profile(
    monkeypatch,
):
    instance = provisioner()

    created = []

    monkeypatch.setattr(
        instance,
        "_exact_object",
        lambda *args, **kwargs: None,
    )

    def fake_post(path, payload):
        obj = {
            **payload,
            "id": f"id-{len(created)}",
        }

        created.append(
            (
                path,
                obj,
            )
        )

        return obj

    monkeypatch.setattr(
        instance,
        "_post",
        fake_post,
    )

    monkeypatch.setattr(
        instance,
        "_patch",
        lambda path, object_id, payload: {
            **payload,
            "id": object_id,
        },
    )

    result = instance.enrich_reservation(reservation())

    inventory = result["vpn_inventory"]

    assert inventory["phase1"]["name"] == "BRANCH-2-PHASE1"

    assert inventory["phase2"]["name"] == "BRANCH-2-PHASE2"

    assert inventory["profile"]["name"] == "BRANCH-2-S2S"

    assert inventory["metadata"]["phase1_proposal"] == "des-sha256"

    assert inventory["metadata"]["phase2_lifetime"] == 3600


def test_rich_inventory_has_named_psks_and_sides(
    monkeypatch,
):
    instance = provisioner()

    monkeypatch.setattr(
        instance,
        "_exact_object",
        lambda *args, **kwargs: None,
    )

    counter = {
        "value": 0,
    }

    def fake_post(path, payload):
        counter["value"] += 1

        return {
            **payload,
            "id": f"new-{counter['value']}",
        }

    patches = []

    monkeypatch.setattr(
        instance,
        "_post",
        fake_post,
    )

    def fake_patch(
        path,
        object_id,
        payload,
    ):
        patches.append(
            (
                path,
                object_id,
                payload,
            )
        )

        return {
            **payload,
            "id": object_id,
        }

    monkeypatch.setattr(
        instance,
        "_patch",
        fake_patch,
    )

    result = instance.enrich_reservation(reservation())

    placeholders = result["vpn_inventory"]["psk_placeholders"]

    assert placeholders["vpn1"] == "********-BRANCH-2-VPN1-PSK-********"

    assert placeholders["vpn2"] == "********-BRANCH-2-VPN2-PSK-********"

    vpn_patches = [payload for path, _, payload in patches if path == "/api/vpn/vpns/"]

    assert "PALO-ALTO-DC" in (vpn_patches[0]["description"])

    assert "FORTIGATE-BRANCH-2" in (vpn_patches[0]["description"])

    tunnel_patches = [
        payload for path, _, payload in patches if path == "/api/vpn/vpn-tunnels/"
    ]

    assert all(payload["encapsulation"] == "IPsec-Tunnel" for payload in tunnel_patches)
