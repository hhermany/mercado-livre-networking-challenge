from pathlib import Path
import shutil

from src.branch.paloalto_cleanup import (
    generate_paloalto_branch_cleanup,
)
from src.branch.provisioning import BranchProvisioner
from src.devices.paloalto_manager import PaloAltoManager


def _reference_id(value):
    if isinstance(value, dict):
        return value.get("id")
    return value


def _safe_exact(
    provisioner,
    path,
    field,
    value,
):
    try:
        return provisioner._exact_object(
            path,
            field,
            value,
        )
    except Exception:
        return None


def cleanup_nautobot_branch(
    *,
    branch_id,
):
    if branch_id == 1:
        raise ValueError(
            "BRANCH-1 e a golden e nao pode ser destruida."
        )

    provisioner = BranchProvisioner()
    plan = provisioner.plan(branch_id=branch_id)

    deleted = []
    warnings = []

    def remove(
        path,
        obj,
        label,
    ):
        if not obj:
            return

        object_id = obj.get("id")

        if not object_id:
            return

        try:
            provisioner._delete(
                path,
                object_id,
            )
            deleted.append(label)
        except Exception as exc:
            warnings.append(
                f"{label}: {exc}"
            )

    # -------------------------------------------------
    # Descobre IPs antes de remover qualquer referencia
    # -------------------------------------------------
    ip_objects = []

    for tunnel_number, prefix in (
        (1, plan.vpn1_prefix),
        (2, plan.vpn2_prefix),
    ):
        pa_ip, fg_ip = provisioner._overlay_hosts(
            prefix
        )

        for role, address in (
            ("PA", f"{pa_ip}/30"),
            ("FG", f"{fg_ip}/30"),
        ):
            obj = _safe_exact(
                provisioner,
                "/api/ipam/ip-addresses/",
                "address",
                address,
            )

            if obj:
                ip_objects.append(
                    (
                        obj,
                        (
                            f"VPN{tunnel_number} "
                            f"{role} IP {address}"
                        ),
                    )
                )

    ip_ids = {
        obj["id"]
        for obj, _label in ip_objects
        if obj.get("id")
    }

    # -------------------------------------------------
    # 1. VPN tunnels
    # -------------------------------------------------
    for number in (1, 2):
        name = f"{plan.name}-VPN{number}"

        obj = _safe_exact(
            provisioner,
            "/api/vpn/vpn-tunnels/",
            "name",
            name,
        )

        remove(
            "/api/vpn/vpn-tunnels/",
            obj,
            f"VPN Tunnel {name}",
        )

    # -------------------------------------------------
    # 2. Tunnel endpoints
    # -------------------------------------------------
    try:
        endpoints = provisioner._get(
            "/api/vpn/vpn-tunnel-endpoints/",
        ).get(
            "results",
            [],
        )

        for endpoint in endpoints:
            source_id = _reference_id(
                endpoint.get(
                    "source_ipaddress"
                )
            )

            if source_id in ip_ids:
                remove(
                    (
                        "/api/vpn/"
                        "vpn-tunnel-endpoints/"
                    ),
                    endpoint,
                    (
                        "VPN Endpoint "
                        f"{endpoint.get('id')}"
                    ),
                )
    except Exception as exc:
        warnings.append(
            f"VPN endpoints: {exc}"
        )

    # -------------------------------------------------
    # 3. VPN objects
    # -------------------------------------------------
    for number in (1, 2):
        name = f"{plan.name}-VPN{number}"

        obj = _safe_exact(
            provisioner,
            "/api/vpn/vpns/",
            "name",
            name,
        )

        remove(
            "/api/vpn/vpns/",
            obj,
            f"VPN {name}",
        )

    # -------------------------------------------------
    # 4. Policies criadas para a branch
    # -------------------------------------------------
    phase2_name = f"{plan.name}-PHASE2"
    phase1_name = f"{plan.name}-PHASE1"

    phase2 = _safe_exact(
        provisioner,
        "/api/vpn/vpn-phase-2-policies/",
        "name",
        phase2_name,
    )

    remove(
        "/api/vpn/vpn-phase-2-policies/",
        phase2,
        f"Phase2 {phase2_name}",
    )

    phase1 = _safe_exact(
        provisioner,
        "/api/vpn/vpn-phase-1-policies/",
        "name",
        phase1_name,
    )

    remove(
        "/api/vpn/vpn-phase-1-policies/",
        phase1,
        f"Phase1 {phase1_name}",
    )

    # -------------------------------------------------
    # 5. IP addresses
    # -------------------------------------------------
    for obj, label in ip_objects:
        remove(
            "/api/ipam/ip-addresses/",
            obj,
            label,
        )

    # -------------------------------------------------
    # 6. Prefixos
    # -------------------------------------------------
    for prefix, _description in (
        provisioner.resources_for_plan(
            plan
        )
    ):
        obj = _safe_exact(
            provisioner,
            "/api/ipam/prefixes/",
            "prefix",
            prefix,
        )

        remove(
            "/api/ipam/prefixes/",
            obj,
            f"Prefix {prefix}",
        )

    return {
        "deleted": deleted,
        "warnings": warnings,
    }


def destroy_branch_deployment(
    *,
    branch_id,
    paloalto_host,
    paloalto_username,
    paloalto_password,
    generated_root="generated",
):
    if branch_id == 1:
        raise ValueError(
            "BRANCH-1 e a golden e nao pode ser destruida."
        )

    cleanup_config = (
        generate_paloalto_branch_cleanup(
            branch_id
        )
    )

    paloalto = PaloAltoManager(
        host=paloalto_host,
        username=paloalto_username,
        password=paloalto_password,
    )

    paloalto_result = (
        paloalto.destroy_configuration(
            cleanup_config
        )
    )

    nautobot = cleanup_nautobot_branch(
        branch_id=branch_id
    )

    output_dir = (
        Path(generated_root)
        / f"BRANCH-{branch_id}"
    )

    artifacts_removed = False

    if not nautobot["warnings"]:
        if output_dir.exists():
            shutil.rmtree(output_dir)

        artifacts_removed = True

    return {
        "branch_id": branch_id,
        "paloalto": paloalto_result,
        "nautobot": nautobot,
        "artifacts_removed": artifacts_removed,
    }
