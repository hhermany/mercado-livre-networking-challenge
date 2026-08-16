import pytest

from src.branch.provisioning import (
    BranchProvisioner,
)


def build_provisioner():
    return BranchProvisioner.__new__(BranchProvisioner)


def test_ensure_reserved_reuses_existing(
    monkeypatch,
):
    provisioner = build_provisioner()

    existing = {
        "plan": object(),
        "objects": {
            "prefixes": [],
        },
        "created": False,
    }

    monkeypatch.setattr(
        provisioner,
        "_load_existing_reservation",
        lambda branch_id: existing,
    )

    def forbidden_reserve(*args, **kwargs):
        raise AssertionError("Nao deve reservar novamente.")

    monkeypatch.setattr(
        provisioner,
        "reserve",
        forbidden_reserve,
    )

    result = provisioner.ensure_reserved(branch_id=2)

    assert result is existing
    assert result["created"] is False


def test_ensure_reserved_creates_when_missing(
    monkeypatch,
):
    provisioner = build_provisioner()

    monkeypatch.setattr(
        provisioner,
        "_load_existing_reservation",
        lambda branch_id: None,
    )

    monkeypatch.setattr(
        provisioner,
        "reserve",
        lambda branch_id: {
            "plan": object(),
            "objects": {},
            "created": True,
        },
    )

    result = provisioner.ensure_reserved(branch_id=2)

    assert result["created"] is True


def test_partial_existing_reservation_blocks(
    monkeypatch,
):
    provisioner = build_provisioner()

    # Exercita diretamente o comportamento
    # do loader com apenas um prefix presente.
    responses = {
        (
            "/api/ipam/prefixes/",
            "10.0.1.0/24",
        ): {
            "id": "lan",
            "prefix": "10.0.1.0/24",
            "description": "BRANCH-2 LAN",
        },
    }

    def exact(path, field, value):
        return responses.get((path, value))

    monkeypatch.setattr(
        provisioner,
        "_exact_object",
        exact,
    )

    with pytest.raises(
        RuntimeError,
        match="Reserva parcial/inconsistente",
    ):
        provisioner._load_existing_reservation(2)
