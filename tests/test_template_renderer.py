from src.templates.renderer import TemplateRenderer


def test_render_fortigate_ipsec_template() -> None:
    renderer = TemplateRenderer()

    output = renderer.render(
        "fortigate/ipsec_tunnel.j2",
        {
            "tunnel_name": "SITE001-DC01",
            "wan_interface": "port1",
            "remote_public_ip": "198.51.100.10",
            "psk": "test-secret",
        },
    )

    assert 'edit "SITE001-DC01"' in output
    assert 'set interface "port1"' in output
    assert "set remote-gw 198.51.100.10" in output
    assert 'set psksecret "test-secret"' in output


def test_render_paloalto_ipsec_template() -> None:
    renderer = TemplateRenderer()

    output = renderer.render(
        "paloalto/ipsec_tunnel.j2",
        {
            "tunnel_name": "SITE001-DC01",
            "wan_interface": "ethernet1/1",
            "remote_public_ip": "198.51.100.10",
            "psk": "test-secret",
            "tunnel_interface": "tunnel.10",
        },
    )

    assert "set network ike gateway SITE001-DC01" in output
    assert "local-address interface ethernet1/1" in output
    assert "peer-address ip 198.51.100.10" in output
    assert 'pre-shared-key key "test-secret"' in output
    assert "tunnel-interface tunnel.10" in output
