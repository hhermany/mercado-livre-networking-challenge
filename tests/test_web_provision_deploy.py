
import src.switch.service as service
import src.web.app as web_app


class FakeCiscoSwitch:
    instances = []

    def __init__(
        self,
        host,
        username,
        password,
        secret="",
    ):
        self.host = host
        self.username = username
        self.password = password
        self.secret = secret

        self.received_config = None

        self.__class__.instances.append(self)

    def deploy_config(
        self,
        config_text,
    ):
        self.received_config = config_text

        return {
            "success": True,
            "blocks_sent": 3,
            "commands_sent": 7,
            "blocks": [],
            "running_config": ("hostname SW-DEPLOYED\n"),
            "saved": False,
        }


class FakeDevice:
    def __init__(
        self,
        device_id="device-1",
    ):
        self.id = device_id

    def credentials(self):
        return {
            "host": "192.0.2.10",
            "username": "admin",
            "password": "password",
            "secret": "",
        }


def candidate_data():
    return {
        "id": "candidate-1",
        "device_id": "device-1",
        "hostname": "SW-DEPLOYED",
        "config": ("hostname SW-DEPLOYED\n!\naaa new-model\n!\n"),
        "running_config": ("hostname SW-OLD\n"),
    }


def test_service_deploys_exact_candidate(
    monkeypatch,
):
    FakeCiscoSwitch.instances.clear()

    monkeypatch.setattr(
        service,
        "CiscoSwitch",
        FakeCiscoSwitch,
    )

    config = "hostname SW-01\n!\naaa new-model\n!\n"

    result = service.deploy_candidate_config(
        host="192.0.2.10",
        username="admin",
        password="password",
        config_text=config,
    )

    assert result["success"] is True
    assert result["saved"] is False

    assert len(FakeCiscoSwitch.instances) == 1

    assert FakeCiscoSwitch.instances[0].received_config == config


def test_endpoint_deploys_stored_candidate(
    monkeypatch,
):
    web_app._provision_candidates.clear()

    web_app._provision_candidates["candidate-1"] = candidate_data()

    monkeypatch.setattr(
        web_app.device_manager,
        "get",
        lambda device_id: FakeDevice(device_id),
    )

    captured = {}

    def fake_deploy(
        **kwargs,
    ):
        captured.update(kwargs)

        return {
            "success": True,
            "blocks_sent": 4,
            "commands_sent": 12,
            "blocks": [],
            "running_config": ("hostname SW-DEPLOYED\n"),
            "saved": False,
        }

    monkeypatch.setattr(
        web_app,
        "deploy_candidate_config",
        fake_deploy,
    )

    response = web_app.app.test_client().post(
        "/api/provision/candidates/candidate-1/deploy"
    )

    assert response.status_code == 200

    data = response.get_json()

    assert data["success"] is True
    assert data["blocks_sent"] == 4
    assert data["commands_sent"] == 12
    assert data["saved"] is False

    assert captured["config_text"] == candidate_data()["config"]

    stored = web_app._provision_candidates["candidate-1"]

    assert stored["running_config_after_deploy"] == "hostname SW-DEPLOYED\n"


def test_endpoint_does_not_regenerate_candidate(
    monkeypatch,
):
    web_app._provision_candidates.clear()

    candidate = candidate_data()

    candidate["config"] = "EXACT STORED CANDIDATE"

    web_app._provision_candidates["candidate-1"] = candidate

    monkeypatch.setattr(
        web_app.device_manager,
        "get",
        lambda device_id: FakeDevice(device_id),
    )

    captured = {}

    def fake_deploy(
        **kwargs,
    ):
        captured.update(kwargs)

        return {
            "success": True,
            "blocks_sent": 1,
            "commands_sent": 1,
            "blocks": [],
            "running_config": "",
            "saved": False,
        }

    monkeypatch.setattr(
        web_app,
        "deploy_candidate_config",
        fake_deploy,
    )

    response = web_app.app.test_client().post(
        "/api/provision/candidates/candidate-1/deploy"
    )

    assert response.status_code == 200

    assert captured["config_text"] == "EXACT STORED CANDIDATE"


def test_endpoint_returns_404_for_unknown_candidate():
    web_app._provision_candidates.clear()

    response = web_app.app.test_client().post(
        "/api/provision/candidates/missing/deploy"
    )

    assert response.status_code == 404

    assert response.get_json()["success"] is False


def test_endpoint_rejects_empty_candidate(
    monkeypatch,
):
    web_app._provision_candidates.clear()

    candidate = candidate_data()
    candidate["config"] = ""

    web_app._provision_candidates["candidate-1"] = candidate

    monkeypatch.setattr(
        web_app.device_manager,
        "get",
        lambda device_id: FakeDevice(device_id),
    )

    response = web_app.app.test_client().post(
        "/api/provision/candidates/candidate-1/deploy"
    )

    assert response.status_code == 400

    assert "sem configuração" in response.get_json()["error"].lower()


def test_endpoint_reports_ios_deploy_failure(
    monkeypatch,
):
    web_app._provision_candidates.clear()

    web_app._provision_candidates["candidate-1"] = candidate_data()

    monkeypatch.setattr(
        web_app.device_manager,
        "get",
        lambda device_id: FakeDevice(device_id),
    )

    def fail_deploy(
        **kwargs,
    ):
        raise RuntimeError(
            "Falha no bloco 7 (radius server RAD1): % Invalid input detected"
        )

    monkeypatch.setattr(
        web_app,
        "deploy_candidate_config",
        fail_deploy,
    )

    response = web_app.app.test_client().post(
        "/api/provision/candidates/candidate-1/deploy"
    )

    assert response.status_code == 400

    error = response.get_json()["error"]

    assert "Deploy falhou" in error
    assert "bloco 7" in error
    assert "Invalid input" in error


def test_endpoint_does_not_mark_failed_deploy_successful(
    monkeypatch,
):
    web_app._provision_candidates.clear()

    candidate = candidate_data()

    web_app._provision_candidates["candidate-1"] = candidate

    monkeypatch.setattr(
        web_app.device_manager,
        "get",
        lambda device_id: FakeDevice(device_id),
    )

    monkeypatch.setattr(
        web_app,
        "deploy_candidate_config",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("IOS rejeitou comando.")),
    )

    response = web_app.app.test_client().post(
        "/api/provision/candidates/candidate-1/deploy"
    )

    assert response.status_code == 400

    stored = web_app._provision_candidates["candidate-1"]

    assert "deploy_result" not in stored

    assert "running_config_after_deploy" not in stored


def test_endpoint_never_reports_saved_startup(
    monkeypatch,
):
    web_app._provision_candidates.clear()

    web_app._provision_candidates["candidate-1"] = candidate_data()

    monkeypatch.setattr(
        web_app.device_manager,
        "get",
        lambda device_id: FakeDevice(device_id),
    )

    monkeypatch.setattr(
        web_app,
        "deploy_candidate_config",
        lambda **kwargs: {
            "success": True,
            "blocks_sent": 2,
            "commands_sent": 4,
            "blocks": [],
            "running_config": "",
            "saved": False,
        },
    )

    response = web_app.app.test_client().post(
        "/api/provision/candidates/candidate-1/deploy"
    )

    assert response.status_code == 200

    assert response.get_json()["saved"] is False
