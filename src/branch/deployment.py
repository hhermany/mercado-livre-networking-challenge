from dataclasses import dataclass
from pathlib import Path

from src.branch.provisioning import (
    BranchProvisioner,
)
from src.devices.fortigate import (
    FortiGateDriver,
)
from src.devices.paloalto_manager import (
    PaloAltoManager,
)


@dataclass(frozen=True)
class BranchDeploymentResult:
    branch_id: int
    name: str
    hostname: str
    nautobot_reserved: bool
    paloalto_applied: bool
    fortigate_applied: bool
    fortigate_validated: bool
    output_dir: str


class BranchDeploymentError(RuntimeError):
    def __init__(
        self,
        message,
        *,
        stage,
        resources_reserved=False,
    ):
        super().__init__(message)

        self.stage = stage
        self.resources_reserved = resources_reserved


def deploy_candidate(
    *,
    candidate,
    device,
    paloalto_host,
    paloalto_username,
    paloalto_password,
    output_root="generated",
):
    """
    Executa o Candidate previamente gerado.

    Ordem:
      1. proteção da golden
      2. reserva exata no Nautobot
      3. salva os artefatos
      4. aplica/commit no Palo Alto
      5. aplica no FortiGate novo
      6. valida hostname do FortiGate

    Se falhar antes de qualquer firewall
    ser alterado, os recursos Nautobot sao
    liberados.

    Se algum firewall ja tiver sido alterado,
    os prefixos PERMANECEM reservados para
    impedir reutilizacao acidental.
    """

    if device.hostname == "FW-BRANCH-1":
        raise BranchDeploymentError(
            "FW-BRANCH-1 e a golden e nao pode receber Deploy de uma nova filial.",
            stage="preflight",
        )

    if device.status != "connected":
        raise BranchDeploymentError(
            "FortiGate alvo nao esta conectado.",
            stage="preflight",
        )

    provisioner = BranchProvisioner()

    reservation = None
    device_changed = False

    stage = "nautobot"

    try:
        reservation = provisioner.reserve(branch_id=(candidate["branch_id"]))

        reserved_plan = reservation["plan"]

        candidate_plan = candidate["plan"]

        exact = {
            "lan_prefix": reserved_plan.lan_prefix,
            "loopback_prefix": reserved_plan.loopback_prefix,
            "vpn1_prefix": reserved_plan.vpn1_prefix,
            "vpn2_prefix": reserved_plan.vpn2_prefix,
        }

        if exact != candidate_plan:
            raise RuntimeError(
                "Plano reservado no Nautobot nao corresponde ao Candidate."
            )

        stage = "artifacts"

        output_dir = Path(output_root) / candidate["name"]

        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        (output_dir / "fortigate.conf").write_text(candidate["fortigate_config"])

        (output_dir / "paloalto.set").write_text(candidate["paloalto_config"])

        stage = "paloalto"

        paloalto = PaloAltoManager(
            host=paloalto_host,
            username=paloalto_username,
            password=paloalto_password,
        )

        paloalto.apply_configuration(candidate["paloalto_config"])

        device_changed = True

        stage = "fortigate"

        fortigate = FortiGateDriver(**device.credentials())

        fortigate.apply_configuration(candidate["fortigate_config"])

        stage = "fortigate-validation"

        fortigate.validate_configuration(expected_hostname=(candidate["hostname"]))

        return BranchDeploymentResult(
            branch_id=(candidate["branch_id"]),
            name=candidate["name"],
            hostname=(candidate["hostname"]),
            nautobot_reserved=True,
            paloalto_applied=True,
            fortigate_applied=True,
            fortigate_validated=True,
            output_dir=str(output_dir),
        )

    except Exception as exc:
        if reservation is not None and not device_changed:
            try:
                provisioner.release(reservation["objects"])
            except Exception:
                pass

        raise BranchDeploymentError(
            (f"Deploy falhou na etapa {stage}: {exc}"),
            stage=stage,
            resources_reserved=(reservation is not None and device_changed),
        ) from exc
