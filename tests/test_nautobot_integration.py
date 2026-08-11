from src.ipam.nautobot import NautobotIPAMProvider


def test_allocate_and_release_prefix() -> None:
    provider = NautobotIPAMProvider()

    prefix = provider.allocate_prefix(
        prefix_length=30,
        description="PYTEST-RBAC-TEST",
    )

    try:
        assert prefix["prefix"].endswith("/30")
        assert prefix["description"] == "PYTEST-RBAC-TEST"
        assert prefix["id"]
    finally:
        provider.release_prefix(prefix["id"])
