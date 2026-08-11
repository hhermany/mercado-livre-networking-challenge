from src.vpn.service import VPNAddressingService


class FakeIPAMProvider:
    def allocate_prefix(self, prefix_length: int, description: str) -> dict:
        assert prefix_length == 30
        assert description == "TEST-TUNNEL"

        return {
            "id": "fake-prefix-id",
            "prefix": "169.255.0.0/30",
        }

    def release_prefix(self, prefix_id: str) -> None:
        assert prefix_id == "fake-prefix-id"


def test_allocate_tunnel() -> None:
    service = VPNAddressingService(FakeIPAMProvider())

    tunnel = service.allocate_tunnel("TEST-TUNNEL")

    assert tunnel.prefix_id == "fake-prefix-id"
    assert tunnel.prefix == "169.255.0.0/30"
    assert tunnel.site_ip == "169.255.0.1"
    assert tunnel.dc_ip == "169.255.0.2"


def test_release_tunnel() -> None:
    service = VPNAddressingService(FakeIPAMProvider())

    service.release_tunnel("fake-prefix-id")
