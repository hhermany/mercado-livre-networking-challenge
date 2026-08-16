import pytest

import src.branch.deployment as deployment
from src.branch.addressing import (
    build_branch_plan,
)


class FakeDevice:
    hostname = "FortiGate-VM"
    status = "connected"

    def credentials(self):
        return {
            "host": "192.0.2.20",
            "username": "admin",
            "password": "password",
        }


class FakeProvisioner:
    released = False

    def ensure_reserved(
        self,
        branch_id=None,
    ):
        plan = build_branch_plan(branch_id)

        return {
            "plan": plan,
            "objects": [
                {
                    "id": "one",
                },
                {
                    "id": "two",
                },
            ],
            "created": True,
        }

    def release(
        self,
        objects,
    ):
        self.released = True


class FakePA:
    applied = []

    def __init__(
        self,
        **kwargs,
    ):
        pass

    def apply_configuration(
        self,
        configuration,
    ):
        self.applied.append(configuration)


class FakeFG:
    applied = []

    def __init__(
        self,
        **kwargs,
    ):
        pass

    def apply_configuration(
        self,
        configuration,
    ):
        self.applied.append(configuration)

    def validate_configuration(
        self,
        *,
        expected_hostname=None,
    ):
        assert expected_hostname == "FW-BRANCH-2"

        return True

    def validate_operational_state(
        self,
        **kwargs,
    ):
        assert kwargs["expected_lan_gateway"] == "10.0.1.254"
        assert kwargs["expected_loopback_ip"] == "172.31.255.2"
        assert kwargs["expected_vpn1_fg_ip"] == "169.255.0.2"
        assert kwargs["expected_vpn2_fg_ip"] == "169.255.0.6"
        assert kwargs["expected_bgp_neighbors"] == (
            "169.255.0.1",
            "169.255.0.5",
        )
        assert kwargs["expected_dhcp_start"] == "10.0.1.1"
        assert kwargs["expected_dhcp_end"] == "10.0.1.10"

        return True


def candidate():
    plan = build_branch_plan(2)

    return {
        "branch_id": 2,
        "name": "BRANCH-2",
        "hostname": "FW-BRANCH-2",
        "plan": {
            "lan_prefix": plan.lan_prefix,
            "loopback_prefix": plan.loopback_prefix,
            "vpn1_prefix": plan.vpn1_prefix,
            "vpn2_prefix": plan.vpn2_prefix,
        },
        "fortigate_config": "config system global\nend\n",
        "paloalto_config": "set network test value\n",
    }


def test_deploy_complete(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        deployment,
        "BranchProvisioner",
        FakeProvisioner,
    )

    monkeypatch.setattr(
        deployment,
        "PaloAltoManager",
        FakePA,
    )

    monkeypatch.setattr(
        deployment,
        "FortiGateDriver",
        FakeFG,
    )

    result = deployment.deploy_candidate(
        candidate=candidate(),
        device=FakeDevice(),
        paloalto_host="192.0.2.1",
        paloalto_username="admin",
        paloalto_password="password",
        output_root=str(tmp_path),
    )

    assert result.nautobot_reserved is True

    assert result.paloalto_applied is True

    assert result.fortigate_applied is True

    assert result.fortigate_validated is True

    assert tmp_path.joinpath(
        "BRANCH-2",
        "fortigate.conf",
    ).exists()

    assert tmp_path.joinpath(
        "BRANCH-2",
        "paloalto.set",
    ).exists()


def test_golden_cannot_be_target():
    device = FakeDevice()
    device.hostname = "FW-BRANCH-1"

    with pytest.raises(
        deployment.BranchDeploymentError,
        match="golden",
    ):
        deployment.deploy_candidate(
            candidate=candidate(),
            device=device,
            paloalto_host="192.0.2.1",
            paloalto_username="admin",
            paloalto_password="password",
        )


def test_existing_reservation_is_not_released_on_pre_device_failure(
    monkeypatch,
    tmp_path,
):
    class ExistingProvisioner(FakeProvisioner):
        released = False

        def ensure_reserved(
            self,
            branch_id=None,
        ):
            plan = build_branch_plan(branch_id)

            return {
                "plan": plan,
                "objects": {
                    "prefixes": [],
                },
                "created": False,
            }

        def release(
            self,
            objects,
        ):
            type(self).released = True

    class BrokenPA:
        def __init__(
            self,
            **kwargs,
        ):
            pass

        def apply_configuration(
            self,
            configuration,
        ):
            raise RuntimeError("simulated PA failure")

    ExistingProvisioner.released = False

    monkeypatch.setattr(
        deployment,
        "BranchProvisioner",
        ExistingProvisioner,
    )

    monkeypatch.setattr(
        deployment,
        "PaloAltoManager",
        BrokenPA,
    )

    with pytest.raises(
        deployment.BranchDeploymentError,
    ):
        deployment.deploy_candidate(
            candidate=candidate(),
            device=FakeDevice(),
            paloalto_host="192.0.2.1",
            paloalto_username="admin",
            paloalto_password="password",
            output_root=str(tmp_path),
        )

    assert ExistingProvisioner.released is False
