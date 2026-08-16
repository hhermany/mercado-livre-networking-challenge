from src.web import app as web_app


def test_home_shows_application_modules():
    client = web_app.app.test_client()

    response = client.get("/")

    assert response.status_code == 200

    html = response.data.decode()

    assert "Networking Challenge" in html
    assert "Multi Switch" in html
    assert "Firewall Deployment" in html

    assert 'href="/switches"' in html
    assert 'href="/firewalls"' in html


def test_firewall_page_exists():
    client = web_app.app.test_client()

    response = client.get("/firewalls")

    assert response.status_code == 200

    html = response.data.decode()

    assert "Firewall Deployment" in html
    assert "Nautobot/IPAM" in html


def test_legacy_device_query_redirects_to_switches():
    client = web_app.app.test_client()

    response = client.get(
        "/?device_id=device-123",
        follow_redirects=False,
    )

    assert response.status_code in {301, 302, 303, 307, 308}

    assert "/switches?device_id=device-123" in response.headers["Location"]
