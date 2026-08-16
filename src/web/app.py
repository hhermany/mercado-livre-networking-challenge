import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from io import BytesIO
from ipaddress import ip_address, ip_network
from time import perf_counter
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from dotenv import load_dotenv
from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from src.branch.bundle import generate_branch_bundle
from src.branch.models import (
    BranchWANInput,
    IPsecPhase1Input,
    IPsecPhase2Input,
)
from src.branch.provisioning import BranchProvisioner
from src.devices.fortigate import discover_managed_fortigate
from src.devices.fortigate_manager import FortiGateManager
from src.devices.paloalto_manager import PaloAltoManager
from src.switch.batch import (
    build_selection_preview,
    combine_interface_selection,
)
from src.switch.cisco import validate_switchport_change
from src.switch.devices import DeviceManager
from src.switch.provisioning import (
    BRANCH_STANDARD_V1,
    SECTION_LABELS,
    SECTION_ORDER,
    BranchVariables,
    InterfaceClassification,
    build_candidate_diff,
    classify_interfaces,
    detect_provision_capabilities,
    discover_provision_port,
    render_branch_candidate,
    validate_provision_port,
)
from src.switch.service import (
    compare_config_texts,
    create_switch_backup,
    deploy_candidate_config,
    discover_managed_switch,
    get_running_config,
    get_startup_config,
    get_switch_interfaces,
    get_switch_l3_interfaces,
    load_managed_switch_workspace,
    provision_interfaces_batch,
    provision_switch,
    run_interface_quick_action,
    run_switch_ping,
    run_switch_traceroute,
    save_running_to_startup,
)
from src.vpn.capabilities import intersect_capabilities

load_dotenv(".env")

app = Flask(__name__)

fortigate_manager = FortiGateManager()

_firewall_candidates = {}


device_manager = DeviceManager(max_workers=4)


def selected_device_id():
    return request.values.get("device_id") or request.headers.get("X-Device-ID")


def is_test_runtime():
    return app.testing


def legacy_test_device():
    """Representa o switch legado somente durante testes."""
    if not is_test_runtime():
        return None

    host = os.getenv("SWITCH_HOST")

    if not host:
        return None

    return {
        "id": "__legacy_test_device__",
        "host": host,
        "hostname": host,
        "username": os.getenv(
            "SWITCH_USERNAME",
            "",
        ),
        "connected": True,
        "status": "connected",
    }


def switch_credentials(
    device_id=None,
):
    device_id = device_id or selected_device_id()

    if device_id and device_id != "__legacy_test_device__":
        try:
            device = device_manager.get(device_id)

        except KeyError as exc:
            raise ValueError("O equipamento selecionado não está cadastrado.") from exc

        return device.credentials()

    # Compatibilidade da suíte histórica.
    # Nunca é usada no Flask operacional.
    if is_test_runtime():
        return {
            "host": os.environ["SWITCH_HOST"],
            "username": os.environ["SWITCH_USERNAME"],
            "password": os.environ["SWITCH_PASSWORD"],
            "secret": os.getenv(
                "SWITCH_SECRET",
                "",
            ),
        }

    raise ValueError("Selecione um equipamento para executar esta operação.")


def load_inventory(
    device_id=None,
):
    effective_device_id = device_id

    if not effective_device_id and is_test_runtime():
        effective_device_id = "__legacy_test_device__"

    if not effective_device_id:
        return [], "", {}, None

    try:
        inventory = get_switch_interfaces(**switch_credentials(effective_device_id))

        return (
            inventory["interfaces"],
            inventory.get(
                "vlan_state",
                "",
            ),
            inventory.get(
                "capabilities",
                {},
            ),
            None,
        )

    except Exception as exc:
        return [], "", {}, str(exc)


def render_page(
    result=None,
    error=None,
    batch_preview=None,
    troubleshooting_result=None,
    troubleshooting_error=None,
    config_result=None,
    config_error=None,
):
    active_device_id = selected_device_id()

    active_device = None

    if active_device_id:
        try:
            active_device = device_manager.get(active_device_id).public()

        except KeyError:
            active_device_id = None

    if active_device is None and is_test_runtime():
        active_device = legacy_test_device()

        if active_device:
            active_device_id = "__legacy_test_device__"

    (
        interfaces,
        vlan_state,
        capabilities,
        inventory_error,
    ) = load_inventory(active_device_id)

    return render_template(
        "index.html",
        result=result,
        error=error,
        interfaces=interfaces,
        vlan_state=vlan_state,
        inventory_error=inventory_error,
        capabilities=capabilities,
        batch_preview=batch_preview,
        troubleshooting_result=troubleshooting_result,
        troubleshooting_error=troubleshooting_error,
        config_result=config_result,
        config_error=config_error,
        active_device_id=active_device_id,
        active_device=active_device,
    )


@app.context_processor
def inject_device_template_context():
    """
    Garante contexto de device também para rotas históricas
    que ainda renderizam index.html diretamente.
    """

    if is_test_runtime():
        return {
            "active_device": (legacy_test_device()),
            "active_device_id": ("__legacy_test_device__"),
        }

    return {
        "active_device": None,
        "active_device_id": None,
    }


def parse_vlans():
    vlans = []

    for row in ("1", "2", "3"):
        vlan_id = request.form.get(
            f"vlan{row}_id",
            "",
        ).strip()

        vlan_name = request.form.get(
            f"vlan{row}_name",
            "",
        ).strip()

        if not vlan_id and not vlan_name:
            continue

        if not vlan_id or not vlan_name:
            raise ValueError("Para configurar uma VLAN, informe ID e nome.")

        vlans.append((int(vlan_id), vlan_name))

    return vlans


def parse_interface_configuration(
    prefix="",
):
    def field(name):
        return request.form.get(
            f"{prefix}{name}",
            "",
        ).strip()

    access_raw = field("access_vlan")

    voice_raw = field("voice_vlan")

    access_vlan = int(access_raw) if access_raw else None

    voice_vlan = int(voice_raw) if voice_raw else None

    description = field("description") or None

    remove_description = request.form.get(f"{prefix}remove_description") == "on"

    remove_voice_vlan = request.form.get(f"{prefix}remove_voice_vlan") == "on"

    admin_state = field("admin_state") or None

    portfast_state = field("portfast_state") or None

    if portfast_state not in (
        None,
        "enable",
        "disable",
    ):
        raise ValueError("PortFast inválido.")

    if description is not None and remove_description:
        raise ValueError(
            "Para Description, escolha configurar um texto "
            "ou remover a descrição atual."
        )

    if voice_vlan is not None and remove_voice_vlan:
        raise ValueError(
            "Para Voice VLAN, escolha configurar um número "
            "ou remover a configuração atual."
        )

    return {
        "access_vlan": access_vlan,
        "voice_vlan": voice_vlan,
        "remove_voice_vlan": remove_voice_vlan,
        "description": description,
        "remove_description": remove_description,
        "admin_state": admin_state,
        "portfast_state": portfast_state,
    }


@app.get("/api/devices")
def api_list_devices():
    return {
        "devices": (device_manager.list()),
    }


@app.post("/api/devices")
def api_add_device():
    payload = request.get_json(silent=True) or request.form

    try:
        device = device_manager.upsert(
            host=payload.get("host"),
            username=payload.get("username"),
            password=payload.get("password"),
            secret=payload.get(
                "secret",
                "",
            ),
        )

        return {
            "success": True,
            "device": device.public(),
        }, 201

    except ValueError as exc:
        return {
            "success": False,
            "error": str(exc),
        }, 400


@app.get("/api/devices/<device_id>")
def api_get_device(
    device_id,
):
    try:
        device = device_manager.get(device_id)

        return {
            "success": True,
            "device": device.public(),
        }

    except KeyError:
        return {
            "success": False,
            "error": "Equipamento não encontrado.",
        }, 404


@app.delete("/api/devices/<device_id>")
def api_remove_device(
    device_id,
):
    try:
        device = device_manager.remove(device_id)

        return {
            "success": True,
            "device": device.public(),
        }

    except KeyError:
        return {
            "success": False,
            "error": ("Equipamento não encontrado."),
        }, 404


_provision_candidates = {}


@app.get("/api/provision/devices")
def api_provision_devices():
    devices = [device.public() for device in device_manager.objects()]

    return jsonify(
        {
            "devices": devices,
        }
    )


def _normalize_provision_interface_name(
    interface_name,
):
    """
    Normaliza nomes Cisco para correlação L2 x L3.

    Exemplos:
        GigabitEthernet0/0 -> gi0/0
        Gi0/0              -> gi0/0
        FastEthernet0/1    -> fa0/1
        TenGigabitEthernet1/0/1 -> te1/0/1
    """
    value = str(interface_name or "").strip()

    lowered = value.lower()

    prefixes = (
        (
            "tengigabitethernet",
            "te",
        ),
        (
            "gigabitethernet",
            "gi",
        ),
        (
            "fastethernet",
            "fa",
        ),
        (
            "twentyfivegige",
            "twe",
        ),
        (
            "hundredgige",
            "hu",
        ),
        (
            "ethernet",
            "eth",
        ),
    )

    for long_name, short_name in prefixes:
        if lowered.startswith(long_name):
            return short_name + lowered[len(long_name) :]

    return lowered


def _provision_inventory(
    device,
):
    """
    Inventário exclusivo do Provision.

    L2 é a base.
    L3 enriquece IPs.

    A correlação usa nomes Cisco normalizados para que,
    por exemplo:

        Gi0/0
        GigabitEthernet0/0

    representem a mesma interface.
    """
    inventory = get_switch_interfaces(**device.credentials())

    interfaces = [
        dict(interface) for interface in (inventory.get("interfaces", []) or [])
    ]

    try:
        l3_inventory = get_switch_l3_interfaces(**device.credentials())

    except Exception:
        l3_inventory = {
            "interfaces": [],
        }

    l3_by_name = {}

    for interface in l3_inventory.get("interfaces", []) or []:
        name = str(
            interface.get("name")
            or interface.get("interface")
            or interface.get("port")
            or ""
        ).strip()

        if not name:
            continue

        normalized = _normalize_provision_interface_name(name)

        l3_by_name[normalized] = interface

    for interface in interfaces:
        name = str(
            interface.get("interface")
            or interface.get("name")
            or interface.get("port")
            or ""
        ).strip()

        if not name:
            continue

        normalized = _normalize_provision_interface_name(name)

        l3 = l3_by_name.get(normalized)

        if not l3:
            continue

        ip_address = str(
            l3.get("ip_address") or l3.get("ip") or l3.get("address") or ""
        ).strip()

        if ip_address:
            interface["ip_address"] = ip_address

    return {
        **inventory,
        "interfaces": interfaces,
    }


def _build_provision_profile(
    device,
):
    """
    Constrói uma cópia isolada do Branch Standard v1
    para o equipamento selecionado.

    A baseline global nunca é alterada.

    O preflight define apenas capabilities que realmente
    dependem da sintaxe/plataforma do equipamento.
    """
    capabilities = detect_provision_capabilities(**device.credentials())

    profile = deepcopy(BRANCH_STANDARD_V1)

    profile["domain_command"] = capabilities.domain_command

    return (
        profile,
        capabilities,
    )


@app.post("/api/provision/analyze")
def api_provision_analyze():
    payload = request.get_json(silent=True) or {}

    device_id = str(
        payload.get(
            "device_id",
            "",
        )
        or ""
    ).strip()

    if not device_id:
        return jsonify(
            {
                "success": False,
                "error": ("Selecione um equipamento."),
            }
        ), 400

    try:
        device = device_manager.get(device_id)

        inventory = _provision_inventory(device)

        running_config = get_running_config(**device.credentials())

        interfaces = inventory.get("interfaces", []) or []

        interface_names = [
            str(
                interface.get("interface")
                or interface.get("name")
                or interface.get("port")
                or ""
            ).strip()
            for interface in interfaces
            if str(
                interface.get("interface")
                or interface.get("name")
                or interface.get("port")
                or ""
            ).strip()
        ]

        provision_interface = discover_provision_port(interfaces)

        provision_validation = validate_provision_port(provision_interface)

        return jsonify(
            {
                "success": True,
                "device": device.public(),
                "interfaces": interfaces,
                "interface_names": (interface_names),
                "interface_count": len(interface_names),
                "running_config_captured": (bool(running_config.strip())),
                "provision_port": provision_validation,
            }
        )

    except KeyError:
        return jsonify(
            {
                "success": False,
                "error": ("Equipamento não encontrado."),
            }
        ), 404

    except Exception as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), 500


@app.post("/api/provision/generate")
def api_provision_generate():
    payload = request.get_json(silent=True) or {}

    device_id = str(
        payload.get(
            "device_id",
            "",
        )
        or ""
    ).strip()

    hostname = str(
        payload.get(
            "hostname",
            "",
        )
        or ""
    ).strip()

    management_ip = str(
        payload.get(
            "management_ip",
            "",
        )
        or ""
    ).strip()

    management_mask = str(
        payload.get(
            "management_mask",
            "",
        )
        or ""
    ).strip()

    default_gateway = str(
        payload.get(
            "default_gateway",
            "",
        )
        or ""
    ).strip()

    uplink_interface = str(
        payload.get(
            "uplink_interface",
            "",
        )
        or ""
    ).strip()

    required = {
        "Equipamento": device_id,
        "Hostname": hostname,
        "IP de gerenciamento": management_ip,
        "Máscara": management_mask,
        "Default Gateway": default_gateway,
        "Uplink": uplink_interface,
    }

    missing = [field for field, value in required.items() if not value]

    if missing:
        return jsonify(
            {
                "success": False,
                "error": ("Campos obrigatórios: " + ", ".join(missing) + "."),
            }
        ), 400

    try:
        parsed_management_ip = ip_address(management_ip)

    except ValueError:
        return jsonify(
            {
                "success": False,
                "error": ("IP de gerenciamento inválido."),
            }
        ), 400

    provision_network = ip_network("172.28.255.0/24")

    if parsed_management_ip in provision_network:
        return jsonify(
            {
                "success": False,
                "error": (
                    "O IP de gerenciamento da "
                    "Vlan255 não pode pertencer "
                    "à rede temporária de "
                    "provisionamento "
                    "172.28.255.0/24."
                ),
            }
        ), 400

    try:
        device = device_manager.get(device_id)

        profile, capabilities = _build_provision_profile(device)

        inventory = _provision_inventory(device)

        running_config = get_running_config(**device.credentials())

        interfaces = inventory.get("interfaces", []) or []

        classification = classify_interfaces(
            interfaces,
            uplink_interface=(uplink_interface),
        )

        variables = BranchVariables(
            hostname=hostname,
            management_ip=(management_ip),
            management_mask=(management_mask),
            default_gateway=(default_gateway),
            uplink_interface=(uplink_interface),
        )

        candidate_config = render_branch_candidate(
            variables=variables,
            classification=(classification),
            profile=profile,
        )

        candidate_id = uuid4().hex

        _provision_candidates[candidate_id] = {
            "id": candidate_id,
            "device_id": device_id,
            "device": device.public(),
            "profile": profile["name"],
            "provision_profile": profile,
            "capabilities": capabilities.as_dict(),
            "hostname": hostname,
            "variables": {
                "management_ip": management_ip,
                "management_mask": management_mask,
                "default_gateway": default_gateway,
                "uplink_interface": uplink_interface,
            },
            "classification": {
                "uplink": classification.uplink,
                "provision_port": classification.provision_port,
                "provision_ip": classification.provision_ip,
                "user_ports": classification.user_ports,
                "preserved_ports": classification.preserved_ports,
            },
            "running_config": running_config,
            "enabled_sections": list(SECTION_ORDER),
            "section_labels": SECTION_LABELS,
            "overrides": "",
            "config": candidate_config,
        }

        return jsonify(
            {
                "success": True,
                "candidate_id": candidate_id,
                "profile": profile["name"],
                "capabilities": capabilities.as_dict(),
                "device": device.public(),
                "hostname": hostname,
                "summary": {
                    "interfaces": len(interfaces),
                    "user_ports": len(classification.user_ports),
                    "preserved_ports": len(classification.preserved_ports),
                    "uplink": classification.uplink,
                    "provision_port": classification.provision_port,
                    "provision_ip": classification.provision_ip,
                },
                "config": candidate_config,
            }
        )

    except KeyError:
        return jsonify(
            {
                "success": False,
                "error": ("Equipamento não encontrado."),
            }
        ), 404

    except RuntimeError as exc:
        return jsonify(
            {
                "success": False,
                "error": ("Preflight: " + str(exc)),
            }
        ), 400

    except ValueError as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), 400

    except Exception as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), 500


@app.get("/api/provision/candidates/<candidate_id>")
def api_provision_candidate(
    candidate_id,
):
    candidate = _provision_candidates.get(candidate_id)

    if candidate is None:
        return jsonify(
            {
                "success": False,
                "error": ("Candidate não encontrado."),
            }
        ), 404

    return jsonify(
        {
            "success": True,
            "candidate": candidate,
        }
    )


@app.get("/api/provision/candidates/<candidate_id>/download")
def api_provision_candidate_download(
    candidate_id,
):
    candidate = _provision_candidates.get(candidate_id)

    if candidate is None:
        return jsonify(
            {
                "success": False,
                "error": ("Candidate não encontrado."),
            }
        ), 404

    filename = f"{candidate['hostname']}_Branch-Standard-v1.cfg"

    return send_file(
        BytesIO(candidate["config"].encode("utf-8")),
        mimetype="text/plain",
        as_attachment=True,
        download_name=filename,
    )


@app.post("/api/provision/candidates/<candidate_id>/adjust")
def api_provision_candidate_adjust(
    candidate_id,
):
    candidate = _provision_candidates.get(candidate_id)

    if candidate is None:
        return jsonify(
            {
                "success": False,
                "error": ("Candidate não encontrado."),
            }
        ), 404

    payload = request.get_json(silent=True) or {}

    enabled_sections = payload.get(
        "enabled_sections",
        list(SECTION_ORDER),
    )

    if not isinstance(
        enabled_sections,
        list,
    ):
        return jsonify(
            {
                "success": False,
                "error": ("Lista de seções inválida."),
            }
        ), 400

    unknown_sections = [
        section for section in enabled_sections if section not in SECTION_ORDER
    ]

    if unknown_sections:
        return jsonify(
            {
                "success": False,
                "error": ("Seções inválidas: " + ", ".join(unknown_sections)),
            }
        ), 400

    overrides = str(
        payload.get(
            "overrides",
            "",
        )
        or ""
    ).strip()

    stored_variables = candidate["variables"]

    variables = BranchVariables(
        hostname=candidate["hostname"],
        management_ip=(stored_variables["management_ip"]),
        management_mask=(stored_variables["management_mask"]),
        default_gateway=(stored_variables["default_gateway"]),
        uplink_interface=(stored_variables["uplink_interface"]),
    )

    stored_classification = candidate["classification"]

    classification = InterfaceClassification(
        uplink=(stored_classification["uplink"]),
        provision_port=(stored_classification["provision_port"]),
        provision_ip=(stored_classification.get("provision_ip")),
        user_ports=list(stored_classification["user_ports"]),
        preserved_ports=list(stored_classification["preserved_ports"]),
    )

    profile = candidate.get("provision_profile")

    if profile is None:
        profile = deepcopy(BRANCH_STANDARD_V1)

    config = render_branch_candidate(
        variables=variables,
        classification=(classification),
        profile=profile,
        enabled_sections=(enabled_sections),
        overrides=overrides,
    )

    candidate["enabled_sections"] = list(enabled_sections)

    candidate["overrides"] = overrides

    candidate["config"] = config

    candidate["diff"] = build_candidate_diff(
        candidate["running_config"],
        config,
    )

    return jsonify(
        {
            "success": True,
            "candidate_id": candidate_id,
            "config": config,
            "enabled_sections": enabled_sections,
            "overrides": overrides,
            "diff": candidate["diff"],
        }
    )


@app.get("/api/provision/candidates/<candidate_id>/diff")
def api_provision_candidate_diff(
    candidate_id,
):
    candidate = _provision_candidates.get(candidate_id)

    if candidate is None:
        return jsonify(
            {
                "success": False,
                "error": ("Candidate não encontrado."),
            }
        ), 404

    diff = build_candidate_diff(
        candidate["running_config"],
        candidate["config"],
    )

    candidate["diff"] = diff

    return jsonify(
        {
            "success": True,
            "candidate_id": candidate_id,
            "diff": diff,
        }
    )


@app.post("/api/devices/interfaces/quick-action")
def api_multi_interface_quick_action():
    payload = request.get_json(silent=True) or {}

    selections = payload.get(
        "selections",
        [],
    )

    action = (
        str(
            payload.get(
                "action",
                "",
            )
            or ""
        )
        .strip()
        .lower()
    )

    if action not in {
        "default",
        "bounce",
    }:
        return jsonify(
            {
                "success": False,
                "error": ("Ação de interface inválida."),
            }
        ), 400

    if (
        not isinstance(
            selections,
            list,
        )
        or not selections
    ):
        return jsonify(
            {
                "success": False,
                "error": ("Selecione pelo menos uma interface."),
            }
        ), 400

    grouped = {}

    for item in selections:
        device_id = str(
            item.get(
                "device_id",
                "",
            )
            or ""
        ).strip()

        interface = str(
            item.get(
                "interface",
                "",
            )
            or ""
        ).strip()

        if not device_id or not interface:
            continue

        grouped.setdefault(device_id, []).append(interface)

    if not grouped:
        return jsonify(
            {
                "success": False,
                "error": ("Seleção de interfaces inválida."),
            }
        ), 400

    workers = min(
        device_manager.max_workers,
        len(grouped),
    )

    results = []

    def worker(
        device_id,
        interfaces,
    ):
        device = device_manager.get(device_id)

        result = run_interface_quick_action(
            **device.credentials(),
            interfaces=interfaces,
            action=action,
        )

        return {
            "device": device.public(),
            "success": True,
            "result": result,
        }

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                worker,
                device_id,
                interfaces,
            ): device_id
            for device_id, interfaces in grouped.items()
        }

        for future in as_completed(futures):
            device_id = futures[future]

            try:
                results.append(future.result())

            except Exception as exc:
                try:
                    device = device_manager.get(device_id).public()

                except Exception:
                    device = {
                        "id": device_id,
                        "hostname": device_id,
                        "host": "",
                    }

                results.append(
                    {
                        "device": device,
                        "success": False,
                        "error": str(exc),
                    }
                )

    return jsonify(
        {
            "success": all(
                item.get(
                    "success",
                    False,
                )
                for item in results
            ),
            "action": action,
            "results": results,
        }
    )


@app.post("/api/devices/interfaces/configure")
def api_configure_multi_device_interfaces():
    payload = request.get_json(silent=True) or {}

    selections = payload.get("selections", [])

    if (
        not isinstance(
            selections,
            list,
        )
        or not selections
    ):
        return {
            "success": False,
            "error": ("Selecione pelo menos uma interface."),
        }, 400

    access_vlan = payload.get("access_vlan")

    voice_vlan = payload.get("voice_vlan")

    description = payload.get("description")

    remove_voice_vlan = bool(
        payload.get(
            "remove_voice_vlan",
            False,
        )
    )

    remove_description = bool(
        payload.get(
            "remove_description",
            False,
        )
    )

    admin_state = payload.get("admin_state")

    portfast_state = payload.get("portfast_state")

    if access_vlan in ("", None):
        access_vlan = None
    else:
        try:
            access_vlan = int(access_vlan)

        except (
            TypeError,
            ValueError,
        ):
            return {
                "success": False,
                "error": ("Access VLAN inválida."),
            }, 400

    if voice_vlan in ("", None):
        voice_vlan = None
    else:
        try:
            voice_vlan = int(voice_vlan)

        except (
            TypeError,
            ValueError,
        ):
            return {
                "success": False,
                "error": ("Voice VLAN inválida."),
            }, 400

    if voice_vlan is not None and remove_voice_vlan:
        return {
            "success": False,
            "error": ("Informe uma Voice VLAN ou selecione remover, não ambos."),
        }, 400

    if description and remove_description:
        return {
            "success": False,
            "error": ("Informe uma Description ou selecione remover, não ambos."),
        }, 400

    if admin_state not in (
        None,
        "",
        "up",
        "down",
    ):
        return {
            "success": False,
            "error": ("Estado administrativo inválido."),
        }, 400

    if portfast_state not in (
        None,
        "",
        "enable",
        "disable",
    ):
        return {
            "success": False,
            "error": ("Estado de PortFast inválido."),
        }, 400

    if not any(
        (
            access_vlan is not None,
            voice_vlan is not None,
            remove_voice_vlan,
            bool(description),
            remove_description,
            bool(admin_state),
            bool(portfast_state),
        )
    ):
        return {
            "success": False,
            "error": ("Informe pelo menos uma alteração para aplicar."),
        }, 400

    grouped = {}

    for item in selections:
        device_id = item.get("device_id")

        interface = (
            item.get(
                "interface",
                "",
            )
            or ""
        ).strip()

        if not device_id or not interface:
            return {
                "success": False,
                "error": ("Seleção de interface inválida."),
            }, 400

        grouped.setdefault(device_id, []).append(interface)

    operation_started = perf_counter()

    def configure_device(
        device_id,
        interfaces,
    ):
        device = device_manager.get(device_id)

        worker_started = perf_counter()

        result = provision_interfaces_batch(
            **device.credentials(),
            interfaces=interfaces,
            access_vlan=access_vlan,
            voice_vlan=voice_vlan,
            remove_voice_vlan=remove_voice_vlan,
            description=(description if description else None),
            remove_description=remove_description,
            admin_state=(admin_state if admin_state else None),
            portfast_state=(portfast_state if portfast_state else None),
        )

        worker_finished = perf_counter()

        return {
            "device": device.public(),
            "interfaces": interfaces,
            "result": result,
            "timing": {
                "started_ms": round(
                    (worker_started - operation_started) * 1000,
                    1,
                ),
                "finished_ms": round(
                    (worker_finished - operation_started) * 1000,
                    1,
                ),
                "duration_ms": round(
                    (worker_finished - worker_started) * 1000,
                    1,
                ),
            },
        }

    workers = min(
        8,
        len(grouped),
    )

    results = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                configure_device,
                device_id,
                interfaces,
            ): (
                device_id,
                interfaces,
            )
            for (
                device_id,
                interfaces,
            ) in grouped.items()
        }

        for future in as_completed(futures):
            (
                device_id,
                interfaces,
            ) = futures[future]

            try:
                result = future.result()

                service_result = result.get("result", {})

                service_success = bool(
                    service_result.get(
                        "success",
                        False,
                    )
                )

                results.append(
                    {
                        "success": service_success,
                        **result,
                    }
                )

            except Exception as exc:
                try:
                    device = device_manager.get(device_id).public()

                except KeyError:
                    device = {
                        "id": device_id,
                        "host": device_id,
                        "hostname": None,
                    }

                results.append(
                    {
                        "success": False,
                        "device": device,
                        "interfaces": interfaces,
                        "error": str(exc),
                    }
                )

    operation_finished = perf_counter()

    return {
        "success": all(item["success"] for item in results),
        "results": results,
        "timing": {
            "total_ms": round(
                (operation_finished - operation_started) * 1000,
                1,
            ),
            "workers": workers,
            "devices": len(grouped),
        },
    }


def _multi_configuration_device_ids(
    payload,
):
    device_ids = payload.get(
        "device_ids",
        [],
    )

    if not isinstance(
        device_ids,
        list,
    ):
        raise ValueError("Lista de equipamentos inválida.")

    device_ids = [
        str(device_id).strip() for device_id in device_ids if str(device_id).strip()
    ]

    if not device_ids:
        raise ValueError("Selecione pelo menos um equipamento.")

    # Preserva ordem sem duplicatas.
    return list(dict.fromkeys(device_ids))


def _parallel_configuration_operation(
    device_ids,
    operation,
):
    workers = min(
        device_manager.max_workers,
        len(device_ids),
    )

    operation_started = perf_counter()

    results = []

    def worker(
        device_id,
    ):
        device = device_manager.get(device_id)

        worker_started = perf_counter()

        result = operation(device)

        return {
            "device": device.public(),
            "success": True,
            "result": result,
            "duration_ms": round(
                (perf_counter() - worker_started) * 1000,
                1,
            ),
        }

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                worker,
                device_id,
            ): device_id
            for device_id in device_ids
        }

        for future in as_completed(futures):
            device_id = futures[future]

            try:
                results.append(future.result())

            except Exception as exc:
                try:
                    device = device_manager.get(device_id).public()

                except Exception:
                    device = {
                        "id": device_id,
                        "hostname": device_id,
                        "host": "",
                    }

                results.append(
                    {
                        "device": device,
                        "success": False,
                        "error": str(exc),
                    }
                )

    results.sort(
        key=lambda item: item.get(
            "device",
            {},
        ).get(
            "host",
            "",
        )
    )

    return {
        "success": all(
            item.get(
                "success",
                False,
            )
            for item in results
        ),
        "results": results,
        "timing": {
            "total_ms": round(
                (perf_counter() - operation_started) * 1000,
                1,
            ),
            "workers": workers,
            "devices": len(device_ids),
        },
    }


@app.post("/api/devices/configuration/save")
def api_multi_configuration_save():
    payload = request.get_json(silent=True) or {}

    try:
        device_ids = _multi_configuration_device_ids(payload)

        result = _parallel_configuration_operation(
            device_ids,
            lambda device: save_running_to_startup(**device.credentials()),
        )

        return jsonify(result)

    except Exception as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), 400


@app.post("/api/devices/configuration/backup")
def api_multi_configuration_backup():
    payload = request.get_json(silent=True) or {}

    try:
        device_ids = _multi_configuration_device_ids(payload)

        protocol = (
            str(
                payload.get(
                    "protocol",
                    "local",
                )
                or "local"
            )
            .strip()
            .lower()
        )

        if protocol not in {
            "local",
            "ftp",
            "sftp",
            "tftp",
        }:
            raise ValueError("Protocolo de backup inválido.")

        backup_host = (
            str(
                payload.get(
                    "backup_host",
                    "",
                )
                or ""
            ).strip()
            or None
        )

        backup_port = (
            str(
                payload.get(
                    "backup_port",
                    "",
                )
                or ""
            ).strip()
            or None
        )

        backup_username = (
            str(
                payload.get(
                    "backup_username",
                    "",
                )
                or ""
            ).strip()
            or None
        )

        backup_password = (
            payload.get(
                "backup_password",
                "",
            )
            or None
        )

        remote_directory = (
            str(
                payload.get(
                    "remote_directory",
                    "/",
                )
                or "/"
            ).strip()
            or "/"
        )

        result = _parallel_configuration_operation(
            device_ids,
            lambda device: create_switch_backup(
                **device.credentials(),
                protocol=protocol,
                backup_host=backup_host,
                backup_port=backup_port,
                backup_username=backup_username,
                backup_password=backup_password,
                remote_directory=remote_directory,
            ),
        )

        result["protocol"] = protocol

        return jsonify(result)

    except Exception as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), 400


@app.post("/api/devices/configuration/download")
def api_multi_configuration_download():
    payload = request.get_json(silent=True) or {}

    try:
        device_ids = _multi_configuration_device_ids(payload)

        config_type = (
            str(
                payload.get(
                    "config_type",
                    "running",
                )
                or "running"
            )
            .strip()
            .lower()
        )

        if config_type not in {
            "running",
            "startup",
        }:
            raise ValueError("Tipo de configuração inválido.")

        from src.switch.configuration import (
            build_backup_filename,
            extract_hostname,
            normalize_config_text,
        )

        def collect(
            device,
        ):
            credentials = device.credentials()

            if config_type == "running":
                config = get_running_config(**credentials)

            else:
                config = get_startup_config(**credentials)

            hostname = extract_hostname(config) or device.hostname or device.host

            filename = build_backup_filename(
                hostname=hostname,
                config_type=config_type,
            )

            return {
                "hostname": hostname,
                "filename": filename,
                "content": normalize_config_text(config),
            }

        collected = _parallel_configuration_operation(
            device_ids,
            collect,
        )

        failures = [item for item in collected["results"] if not item.get("success")]

        if failures:
            return jsonify(collected), 500

        files = [item["result"] for item in collected["results"]]

        # Um switch:
        # download direto do .cfg.
        if len(files) == 1:
            item = files[0]

            content = item["content"].encode("utf-8")

            return send_file(
                BytesIO(content),
                as_attachment=True,
                download_name=(item["filename"]),
                mimetype=("text/plain; charset=utf-8"),
            )

        # Vários switches:
        # um único ZIP previsível para o browser.
        buffer = BytesIO()

        with ZipFile(
            buffer,
            "w",
            compression=ZIP_DEFLATED,
        ) as archive:
            for item in files:
                archive.writestr(
                    item["filename"],
                    item["content"],
                )

        buffer.seek(0)

        return send_file(
            buffer,
            as_attachment=True,
            download_name=(f"switches_{config_type}_configs.zip"),
            mimetype="application/zip",
        )

    except Exception as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), 400


@app.post("/api/devices/configuration/diff")
def api_multi_configuration_diff():
    payload = request.get_json(silent=True) or {}

    try:
        device_ids = _multi_configuration_device_ids(payload)

        def compare(
            device,
        ):
            startup = get_startup_config(**device.credentials())

            running = get_running_config(**device.credentials())

            diff = compare_config_texts(
                left_text=startup,
                right_text=running,
                left_label="startup-config",
                right_label="running-config",
            )

            return {
                "diff": diff,
            }

        result = _parallel_configuration_operation(
            device_ids,
            compare,
        )

        return jsonify(result)

    except Exception as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), 400


def _multi_tshoot_positive_int(
    payload,
    field,
    label,
    default,
    maximum=None,
):
    raw = payload.get(
        field,
        default,
    )

    try:
        value = int(raw)
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise ValueError(f"{label} deve ser um número inteiro.") from exc

    if value < 1:
        raise ValueError(f"{label} deve ser maior que zero.")

    if maximum is not None and value > maximum:
        raise ValueError(f"{label} deve ser no máximo {maximum}.")

    return value


def _multi_tshoot_operations(
    payload,
):
    operations = payload.get(
        "operations",
        [],
    )

    if (
        not isinstance(
            operations,
            list,
        )
        or not operations
    ):
        raise ValueError("Selecione pelo menos um equipamento.")

    normalized = []

    seen = set()

    for operation in operations:
        device_id = str(
            operation.get(
                "device_id",
                "",
            )
            or ""
        ).strip()

        source_interface = str(
            operation.get(
                "source_interface",
                "",
            )
            or ""
        ).strip()

        if not device_id:
            raise ValueError("Equipamento inválido.")

        if not source_interface:
            raise ValueError("Selecione a interface L3 de origem de cada equipamento.")

        if device_id in seen:
            continue

        seen.add(device_id)

        normalized.append(
            {
                "device_id": device_id,
                "source_interface": source_interface,
            }
        )

    return normalized


def _parallel_tshoot_operation(
    operations,
    callback,
):
    workers = min(
        device_manager.max_workers,
        len(operations),
    )

    started = perf_counter()

    results = []

    def worker(
        operation,
    ):
        device = device_manager.get(operation["device_id"])

        worker_started = perf_counter()

        result = callback(
            device,
            operation,
        )

        return {
            "device": device.public(),
            "success": True,
            "result": result,
            "duration_ms": round(
                (perf_counter() - worker_started) * 1000,
                1,
            ),
        }

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                worker,
                operation,
            ): operation
            for operation in operations
        }

        for future in as_completed(futures):
            operation = futures[future]

            try:
                results.append(future.result())

            except Exception as exc:
                device_id = operation["device_id"]

                try:
                    device = device_manager.get(device_id).public()

                except Exception:
                    device = {
                        "id": device_id,
                        "hostname": device_id,
                        "host": "",
                    }

                results.append(
                    {
                        "device": device,
                        "success": False,
                        "error": str(exc),
                    }
                )

    results.sort(
        key=lambda item: item.get(
            "device",
            {},
        ).get(
            "host",
            "",
        )
    )

    return {
        "success": all(
            item.get(
                "success",
                False,
            )
            for item in results
        ),
        "results": results,
        "timing": {
            "total_ms": round(
                (perf_counter() - started) * 1000,
                1,
            ),
            "workers": workers,
            "devices": len(operations),
        },
    }


@app.post("/api/devices/troubleshooting/interfaces")
def api_multi_tshoot_interfaces():
    payload = request.get_json(silent=True) or {}

    device_ids = payload.get(
        "device_ids",
        [],
    )

    if (
        not isinstance(
            device_ids,
            list,
        )
        or not device_ids
    ):
        return jsonify(
            {
                "success": False,
                "error": "Selecione pelo menos um equipamento.",
            }
        ), 400

    device_ids = list(
        dict.fromkeys(str(item).strip() for item in device_ids if str(item).strip())
    )

    workers = min(
        device_manager.max_workers,
        len(device_ids),
    )

    results = []

    def worker(
        device_id,
    ):
        device = device_manager.get(device_id)

        inventory = get_switch_l3_interfaces(**device.credentials())

        return {
            "device": device.public(),
            "success": True,
            "interfaces": inventory.get(
                "interfaces",
                [],
            ),
        }

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                worker,
                device_id,
            ): device_id
            for device_id in device_ids
        }

        for future in as_completed(futures):
            device_id = futures[future]

            try:
                results.append(future.result())

            except Exception as exc:
                try:
                    device = device_manager.get(device_id).public()

                except Exception:
                    device = {
                        "id": device_id,
                        "hostname": device_id,
                        "host": "",
                    }

                results.append(
                    {
                        "device": device,
                        "success": False,
                        "interfaces": [],
                        "error": str(exc),
                    }
                )

    results.sort(
        key=lambda item: item.get(
            "device",
            {},
        ).get(
            "host",
            "",
        )
    )

    return jsonify(
        {
            "success": all(
                item.get(
                    "success",
                    False,
                )
                for item in results
            ),
            "results": results,
        }
    )


@app.post("/api/devices/troubleshooting/ping")
def api_multi_tshoot_ping():
    payload = request.get_json(silent=True) or {}

    try:
        raw_operations = payload.get(
            "operations",
            [],
        )

        if (
            not isinstance(
                raw_operations,
                list,
            )
            or not raw_operations
        ):
            raise ValueError("Selecione pelo menos um equipamento.")

        operations = []

        total_parallelism = 0

        seen = set()

        for raw in raw_operations:
            device_id = str(
                raw.get(
                    "device_id",
                    "",
                )
                or ""
            ).strip()

            source_interface = str(
                raw.get(
                    "source_interface",
                    "",
                )
                or ""
            ).strip()

            targets = str(
                raw.get(
                    "targets",
                    "",
                )
                or ""
            ).strip()

            if not device_id:
                raise ValueError("Equipamento inválido.")

            if device_id in seen:
                continue

            seen.add(device_id)

            if not source_interface:
                raise ValueError("Selecione uma Source L3 para cada equipamento.")

            if not targets:
                raise ValueError(
                    "Informe o destino de Ping para cada equipamento selecionado."
                )

            try:
                repeat = int(
                    raw.get(
                        "repeat",
                        5,
                    )
                )

                timeout = int(
                    raw.get(
                        "timeout",
                        2,
                    )
                )

                size = int(
                    raw.get(
                        "size",
                        100,
                    )
                )

                parallelism = int(
                    raw.get(
                        "concurrency",
                        1,
                    )
                )

            except (
                TypeError,
                ValueError,
            ) as exc:
                raise ValueError("Parâmetros numéricos do Ping são inválidos.") from exc

            if repeat < 1:
                raise ValueError("Pacotes deve ser maior que zero.")

            if timeout < 1:
                raise ValueError("Timeout deve ser maior que zero.")

            if size < 1:
                raise ValueError("Tamanho deve ser maior que zero.")

            if not 1 <= parallelism <= 8:
                raise ValueError("Paralelismo deve estar entre 1 e 8.")

            total_parallelism += parallelism

            operations.append(
                {
                    "device_id": device_id,
                    "source_interface": source_interface,
                    "targets": targets,
                    "repeat": repeat,
                    "timeout": timeout,
                    "size": size,
                    #
                    # O service antigo continua chamando
                    # este parâmetro de concurrency.
                    #
                    "concurrency": parallelism,
                    "df_bit": bool(
                        raw.get(
                            "df_bit",
                            False,
                        )
                    ),
                }
            )

        if total_parallelism > 8:
            raise ValueError(
                "O paralelismo total dos equipamentos não pode ultrapassar 8."
            )

        result = _parallel_tshoot_operation(
            operations,
            lambda device, operation: run_switch_ping(
                **device.credentials(),
                source_interface=(operation["source_interface"]),
                #
                # CRÍTICO:
                # destino pertence à operação/switch.
                #
                targets=(operation["targets"]),
                repeat=(operation["repeat"]),
                timeout=(operation["timeout"]),
                size=(operation["size"]),
                df_bit=(operation["df_bit"]),
                concurrency=(operation["concurrency"]),
            ),
        )

        result["total_parallelism"] = total_parallelism

        return jsonify(result)

    except ValueError as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), 400

    except Exception as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), 500


@app.post("/api/devices/troubleshooting/traceroute")
def api_multi_tshoot_traceroute():
    payload = request.get_json(silent=True) or {}

    try:
        raw_operations = payload.get(
            "operations",
            [],
        )

        if (
            not isinstance(
                raw_operations,
                list,
            )
            or not raw_operations
        ):
            raise ValueError("Selecione pelo menos um equipamento.")

        operations = []

        seen = set()

        for raw in raw_operations:
            device_id = str(
                raw.get(
                    "device_id",
                    "",
                )
                or ""
            ).strip()

            source_interface = str(
                raw.get(
                    "source_interface",
                    "",
                )
                or ""
            ).strip()

            destination = str(
                raw.get(
                    "destination",
                    "",
                )
                or ""
            ).strip()

            if not device_id:
                raise ValueError("Equipamento inválido.")

            if device_id in seen:
                continue

            seen.add(device_id)

            if not source_interface:
                raise ValueError("Selecione uma Source L3 para cada equipamento.")

            if not destination:
                raise ValueError(
                    "Informe o destino do Traceroute para cada equipamento."
                )

            try:
                timeout = int(
                    raw.get(
                        "timeout",
                        1,
                    )
                )

                probe_count = int(
                    raw.get(
                        "probe_count",
                        3,
                    )
                )

                max_ttl = int(
                    raw.get(
                        "max_ttl",
                        20,
                    )
                )

            except (
                TypeError,
                ValueError,
            ) as exc:
                raise ValueError("Parâmetros do Traceroute inválidos.") from exc

            if timeout < 1:
                raise ValueError("Timeout deve ser maior que zero.")

            if probe_count < 1:
                raise ValueError("Probes por salto deve ser maior que zero.")

            if max_ttl < 1:
                raise ValueError("TTL máximo deve ser maior que zero.")

            operations.append(
                {
                    "device_id": device_id,
                    "source_interface": source_interface,
                    "destination": destination,
                    "timeout": timeout,
                    "probe_count": probe_count,
                    "max_ttl": max_ttl,
                }
            )

        result = _parallel_tshoot_operation(
            operations,
            lambda device, operation: run_switch_traceroute(
                **device.credentials(),
                source_interface=(operation["source_interface"]),
                destination=(operation["destination"]),
                timeout=(operation["timeout"]),
                probe_count=(operation["probe_count"]),
                max_ttl=(operation["max_ttl"]),
            ),
        )

        return jsonify(result)

    except ValueError as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), 400

    except Exception as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), 500


@app.post("/api/devices/general/configure")
def api_configure_multi_device_general():
    payload = request.get_json(silent=True) or {}

    operations = payload.get("operations", [])

    if (
        not isinstance(
            operations,
            list,
        )
        or not operations
    ):
        return {
            "success": False,
            "error": ("Selecione pelo menos um equipamento."),
        }, 400

    normalized = []

    for operation in operations:
        device_id = operation.get("device_id")

        hostname = (operation.get("hostname", "") or "").strip() or None

        raw_vlans = operation.get("vlans", [])

        if not device_id:
            return {
                "success": False,
                "error": ("Equipamento inválido."),
            }, 400

        if not isinstance(
            raw_vlans,
            list,
        ):
            return {
                "success": False,
                "error": ("Lista de VLANs inválida."),
            }, 400

        vlans = []

        for vlan in raw_vlans:
            vlan_id = vlan.get("id")

            vlan_name = (vlan.get("name", "") or "").strip()

            if (
                vlan_id
                in (
                    "",
                    None,
                )
                and not vlan_name
            ):
                continue

            try:
                vlan_id = int(vlan_id)
            except (
                TypeError,
                ValueError,
            ):
                return {
                    "success": False,
                    "error": ("VLAN ID inválida."),
                }, 400

            if not 1 <= vlan_id <= 4094:
                return {
                    "success": False,
                    "error": (f"VLAN {vlan_id} fora do intervalo 1-4094."),
                }, 400

            if not vlan_name:
                return {
                    "success": False,
                    "error": (f"Informe o nome da VLAN {vlan_id}."),
                }, 400

            vlans.append(
                (
                    vlan_id,
                    vlan_name,
                )
            )

        if not hostname and not vlans:
            return {
                "success": False,
                "error": (
                    "Informe hostname e/ou VLAN para cada equipamento selecionado."
                ),
            }, 400

        normalized.append(
            {
                "device_id": device_id,
                "hostname": hostname,
                "vlans": vlans,
            }
        )

    operation_started = perf_counter()

    def configure_device(
        operation,
    ):
        device = device_manager.get(operation["device_id"])

        worker_started = perf_counter()

        result = provision_switch(
            **device.credentials(),
            hostname=operation["hostname"],
            vlans=operation["vlans"],
        )

        if result.get("success") and operation["hostname"]:
            device.hostname = operation["hostname"]

        return {
            "device_id": operation["device_id"],
            "host": device.host,
            "hostname": (operation["hostname"] or device.hostname or device.host),
            "success": bool(result.get("success")),
            "missing": result.get(
                "missing",
                [],
            ),
            "changes": result.get(
                "changes",
                [],
            ),
            "backup": result.get("backup"),
            "duration_ms": round(
                (perf_counter() - worker_started) * 1000,
                1,
            ),
        }

    workers = min(
        device_manager.max_workers,
        len(normalized),
    )

    results = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                configure_device,
                operation,
            ): operation
            for operation in normalized
        }

        for future in as_completed(futures):
            operation = futures[future]

            try:
                results.append(future.result())

            except Exception as exc:
                device_id = operation["device_id"]

                try:
                    device = device_manager.get(device_id)

                    host = device.host
                    hostname = device.hostname or device.host

                except KeyError:
                    host = ""
                    hostname = device_id

                results.append(
                    {
                        "device_id": device_id,
                        "host": host,
                        "hostname": hostname,
                        "success": False,
                        "missing": [],
                        "changes": [],
                        "error": str(exc),
                    }
                )

    results.sort(key=lambda item: item.get("host", ""))

    success = all(item.get("success") for item in results)

    return {
        "success": success,
        "results": results,
        "duration_ms": round(
            (perf_counter() - operation_started) * 1000,
            1,
        ),
        "workers": workers,
        "devices": len(normalized),
    }


@app.post("/api/devices/workspace")
def api_devices_workspace():
    payload = request.get_json(silent=True) or {}

    device_ids = payload.get(
        "device_ids",
        [],
    )

    if not isinstance(
        device_ids,
        list,
    ):
        return {
            "success": False,
            "error": ("device_ids deve ser uma lista."),
        }, 400

    if not device_ids:
        return {
            "success": False,
            "error": ("Selecione pelo menos um equipamento."),
        }, 400

    try:
        results = device_manager.discover_many(
            load_managed_switch_workspace,
            device_ids=device_ids,
        )

    except KeyError:
        return {
            "success": False,
            "error": ("Um dos equipamentos selecionados não está mais cadastrado."),
        }, 404

    return {
        "success": True,
        "devices": results,
    }


@app.post("/api/devices/discover")
def api_discover_devices():
    payload = request.get_json(silent=True) or {}

    device_ids = payload.get("device_ids")

    results = device_manager.discover_many(
        discover_managed_switch,
        device_ids=device_ids,
    )

    return {
        "success": True,
        "devices": results,
    }


@app.get("/")
def index():
    if request.args.get("device_id"):
        return redirect(
            url_for(
                "switches",
                device_id=request.args.get("device_id"),
            )
        )

    return render_template("home.html")


@app.get("/switches")
def switches():
    return render_page()


@app.get("/api/firewalls")
def api_firewalls():
    return jsonify(
        {
            "success": True,
            "devices": fortigate_manager.list(),
        }
    )


@app.post("/api/firewalls")
def api_add_firewall():
    payload = (
        request.get_json(
            silent=True,
        )
        or {}
    )

    try:
        device = fortigate_manager.upsert(
            host=payload.get("host"),
            username=payload.get("username"),
            password=payload.get("password"),
        )

        discovery = discover_managed_fortigate(device)

        device.hostname = discovery.get("hostname")
        device.status = "connected"
        device.error = None

        fortigate_manager.save(device)

        result = device.public()
        result["version"] = discovery.get("version")
        result["serial"] = discovery.get("serial")

        return jsonify(
            {
                "success": True,
                "device": result,
            }
        )

    except Exception as exc:
        try:
            device.status = "error"
            device.error = str(exc)
        except UnboundLocalError:
            pass

        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), 400


@app.delete("/api/firewalls/<device_id>")
def api_delete_firewall(device_id):
    try:
        fortigate_manager.remove(device_id)

    except KeyError as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), 404

    return jsonify(
        {
            "success": True,
        }
    )


@app.get("/api/firewalls/<device_id>/ipsec-capabilities")
def api_firewall_ipsec_capabilities(
    device_id,
):
    try:
        device = fortigate_manager.get(device_id)

        if device.status != "connected":
            raise ValueError("O FortiGate selecionado nao esta conectado.")

        from src.devices.fortigate import (
            FortiGateDriver,
        )

        driver = FortiGateDriver(**device.credentials())

        fortigate_capabilities = driver.discover_ipsec_capabilities()

        paloalto_host = os.getenv("PALOALTO_HOST", "").strip()
        paloalto_username = os.getenv("PALOALTO_USERNAME", "").strip()
        paloalto_password = os.getenv("PALOALTO_PASSWORD", "")

        if not all(
            (
                paloalto_host,
                paloalto_username,
                paloalto_password,
            )
        ):
            raise ValueError(
                "Palo Alto nao configurado. "
                "Defina PALOALTO_HOST, PALOALTO_USERNAME "
                "e PALOALTO_PASSWORD."
            )

        paloalto = PaloAltoManager(
            host=paloalto_host,
            username=paloalto_username,
            password=paloalto_password,
        )

        paloalto_capabilities = paloalto.discover_ipsec_capabilities()

        compatible = intersect_capabilities(
            fortigate_capabilities,
            paloalto_capabilities,
        )

        return jsonify(
            {
                "success": True,
                "fortigate": {
                    "ike_versions": fortigate_capabilities.ike_versions,
                    "phase1_proposals": (fortigate_capabilities.phase1_proposals),
                    "phase1_dh_groups": (fortigate_capabilities.phase1_dh_groups),
                    "phase2_proposals": (fortigate_capabilities.phase2_proposals),
                    "phase2_dh_groups": (fortigate_capabilities.phase2_dh_groups),
                },
                "paloalto": {
                    "ike_versions": paloalto_capabilities.ike_versions,
                    "phase1_proposals": (paloalto_capabilities.phase1_proposals),
                    "phase1_dh_groups": (paloalto_capabilities.phase1_dh_groups),
                    "phase2_proposals": (paloalto_capabilities.phase2_proposals),
                    "phase2_dh_groups": (paloalto_capabilities.phase2_dh_groups),
                },
                "compatible": {
                    "ike_versions": compatible.ike_versions,
                    "phase1_proposals": compatible.phase1_proposals,
                    "phase1_dh_groups": compatible.phase1_dh_groups,
                    "phase2_proposals": compatible.phase2_proposals,
                    "phase2_dh_groups": compatible.phase2_dh_groups,
                },
                "paloalto_ready": True,
                "message": (
                    "Capabilities FortiGate x Palo Alto calculadas com sucesso."
                ),
            }
        )

    except (
        KeyError,
        ValueError,
        RuntimeError,
    ) as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), 400

    except Exception as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), 500


@app.get("/api/firewalls/provision/plan")
def api_firewall_provision_plan():
    try:
        plan = BranchProvisioner().plan()

        return jsonify(
            {
                "success": True,
                "plan": {
                    "branch_id": plan.branch_id,
                    "name": plan.name,
                    "hostname": plan.hostname,
                    "lan_prefix": plan.lan_prefix,
                    "loopback_prefix": plan.loopback_prefix,
                    "vpn1_prefix": plan.vpn1_prefix,
                    "vpn2_prefix": plan.vpn2_prefix,
                },
            }
        )

    except Exception as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), 400


@app.post("/api/firewalls/provision/candidates")
def api_firewall_provision_candidate():
    payload = (
        request.get_json(
            silent=True,
        )
        or {}
    )

    device_id = str(
        payload.get(
            "device_id",
            "",
        )
        or ""
    ).strip()

    if not device_id:
        return jsonify(
            {
                "success": False,
                "error": "Selecione um FortiGate.",
            }
        ), 400

    try:
        device = fortigate_manager.get(device_id)

        if device.status != "connected":
            raise ValueError("O FortiGate selecionado nao esta conectado.")

        provisioner = BranchProvisioner()

        plan = provisioner.plan()

        hostname = str(
            payload.get(
                "hostname",
                "",
            )
            or plan.hostname
        ).strip()

        wan = BranchWANInput(
            wan1_ip=str(
                payload.get(
                    "wan1_ip",
                    "",
                )
                or ""
            ).strip(),
            wan1_gateway=str(
                payload.get(
                    "wan1_gateway",
                    "",
                )
                or ""
            ).strip(),
            wan2_ip=str(
                payload.get(
                    "wan2_ip",
                    "",
                )
                or ""
            ).strip(),
            wan2_gateway=str(
                payload.get(
                    "wan2_gateway",
                    "",
                )
                or ""
            ).strip(),
        )

        phase1 = IPsecPhase1Input(
            ike_version=2,
            proposal="des-sha256",
            dh_group=14,
            psk=str(
                payload.get(
                    "phase1_psk",
                    "",
                )
                or ""
            ),
        )

        phase2 = IPsecPhase2Input(
            proposal="des-sha256",
            dh_group=14,
        )

        required = {
            "Hostname": hostname,
            "WAN1 IP/prefixo": wan.wan1_ip,
            "WAN1 Gateway": wan.wan1_gateway,
            "WAN2 IP/prefixo": wan.wan2_ip,
            "WAN2 Gateway": wan.wan2_gateway,
            "Phase1 Proposal": phase1.proposal,
            "Phase1 PSK": phase1.psk,
            "Phase2 Proposal": phase2.proposal,
        }

        missing = [name for name, value in required.items() if not value]

        if missing:
            raise ValueError("Campos obrigatorios: " + ", ".join(missing))

        dc_wan1_ip = os.getenv(
            "DC_WAN1_IP",
            "100.64.0.1",
        )

        dc_wan2_ip = os.getenv(
            "DC_WAN2_IP",
            "100.100.0.1",
        )

        bundle = generate_branch_bundle(
            branch_id=plan.branch_id,
            wan=wan,
            phase1=phase1,
            phase2=phase2,
            dc_wan1_ip=dc_wan1_ip,
            dc_wan2_ip=dc_wan2_ip,
            hostname=hostname,
        )

        candidate_id = uuid4().hex

        _firewall_candidates[candidate_id] = {
            "id": candidate_id,
            "device_id": device_id,
            "device": device.public(),
            "branch_id": plan.branch_id,
            "name": plan.name,
            "hostname": bundle.hostname,
            "plan": {
                "lan_prefix": plan.lan_prefix,
                "loopback_prefix": plan.loopback_prefix,
                "vpn1_prefix": plan.vpn1_prefix,
                "vpn2_prefix": plan.vpn2_prefix,
            },
            "wan": {
                "wan1_ip": wan.wan1_ip,
                "wan1_gateway": wan.wan1_gateway,
                "wan2_ip": wan.wan2_ip,
                "wan2_gateway": wan.wan2_gateway,
            },
            "fortigate_config": bundle.fortigate,
            "paloalto_config": bundle.paloalto,
        }

        return jsonify(
            {
                "success": True,
                "candidate_id": candidate_id,
                "branch_id": plan.branch_id,
                "name": plan.name,
                "hostname": bundle.hostname,
                "plan": {
                    "lan_prefix": plan.lan_prefix,
                    "loopback_prefix": plan.loopback_prefix,
                    "vpn1_prefix": plan.vpn1_prefix,
                    "vpn2_prefix": plan.vpn2_prefix,
                },
            }
        )

    except (
        KeyError,
        ValueError,
    ) as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), 400

    except Exception as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), 500


@app.get("/api/firewalls/provision/candidates/<candidate_id>")
def api_firewall_candidate(candidate_id):
    candidate = _firewall_candidates.get(candidate_id)

    if candidate is None:
        return jsonify(
            {
                "success": False,
                "error": "Candidate nao encontrado.",
            }
        ), 404

    return jsonify(
        {
            "success": True,
            "candidate": {
                "id": candidate["id"],
                "device": candidate["device"],
                "branch_id": candidate["branch_id"],
                "name": candidate["name"],
                "hostname": candidate["hostname"],
                "plan": candidate["plan"],
                "wan": candidate["wan"],
                "config": candidate["fortigate_config"],
            },
        }
    )


@app.get("/api/firewalls/provision/candidates/<candidate_id>/download")
def api_firewall_candidate_download(
    candidate_id,
):
    candidate = _firewall_candidates.get(candidate_id)

    if candidate is None:
        return jsonify(
            {
                "success": False,
                "error": "Candidate nao encontrado.",
            }
        ), 404

    filename = candidate["hostname"] + "_Branch.cfg"

    return send_file(
        BytesIO(candidate["fortigate_config"].encode("utf-8")),
        mimetype="text/plain",
        as_attachment=True,
        download_name=filename,
    )


@app.post("/api/firewalls/provision/candidates/<candidate_id>/deploy")
def api_firewall_candidate_deploy(
    candidate_id,
):
    from src.branch.deployment import (
        BranchDeploymentError,
        deploy_candidate,
    )

    candidate = _firewall_candidates.get(candidate_id)

    if candidate is None:
        return jsonify(
            {
                "success": False,
                "error": "Candidate nao encontrado.",
            }
        ), 404

    try:
        device = fortigate_manager.get(candidate["device_id"])

        paloalto_host = os.getenv(
            "PALOALTO_HOST",
            "",
        ).strip()

        paloalto_username = os.getenv(
            "PALOALTO_USERNAME",
            "",
        ).strip()

        paloalto_password = os.getenv(
            "PALOALTO_PASSWORD",
            "",
        )

        if not all(
            (
                paloalto_host,
                paloalto_username,
                paloalto_password,
            )
        ):
            raise ValueError("Palo Alto nao configurado no ambiente.")

        result = deploy_candidate(
            candidate=candidate,
            device=device,
            paloalto_host=(paloalto_host),
            paloalto_username=(paloalto_username),
            paloalto_password=(paloalto_password),
        )

        device.hostname = result.hostname
        device.status = "connected"
        device.error = None

        fortigate_manager.save(device)

        candidate["deployment"] = {
            "success": True,
            "output_dir": result.output_dir,
        }

        return jsonify(
            {
                "success": True,
                "branch_id": result.branch_id,
                "name": result.name,
                "hostname": result.hostname,
                "nautobot_reserved": result.nautobot_reserved,
                "paloalto_applied": result.paloalto_applied,
                "fortigate_applied": result.fortigate_applied,
                "fortigate_validated": result.fortigate_validated,
                "output_dir": result.output_dir,
            }
        )

    except BranchDeploymentError as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
                "stage": exc.stage,
                "resources_reserved": exc.resources_reserved,
            }
        ), 500

    except (
        KeyError,
        ValueError,
    ) as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), 400


@app.get("/firewalls")
def firewalls():
    return render_template("firewalls.html")


@app.post("/")
def stale_root_post():
    return redirect(url_for("switches"))


@app.post("/apply-hostname")
def apply_hostname():
    try:
        hostname = (
            request.form.get(
                "hostname",
                "",
            ).strip()
            or None
        )

        if not hostname:
            raise ValueError("Informe o novo hostname.")

        result = provision_switch(
            **switch_credentials(),
            hostname=hostname,
        )

        return render_page(
            result=result,
        )

    except Exception as exc:
        return render_page(
            error=str(exc),
        )


@app.post("/apply-vlans")
def apply_vlans():
    try:
        vlans = parse_vlans()

        if not vlans:
            raise ValueError("Informe pelo menos uma VLAN.")

        result = provision_switch(
            **switch_credentials(),
            vlans=vlans,
        )

        return render_page(
            result=result,
        )

    except Exception as exc:
        return render_page(
            error=str(exc),
        )


@app.post("/apply-ports")
def apply_ports():
    interfaces, _, capabilities, inventory_error = load_inventory()

    try:
        if inventory_error:
            raise ValueError(
                f"Não foi possível consultar as interfaces do switch: {inventory_error}"
            )

        selected_names = request.form.getlist("interfaces")

        start_interface = (
            request.form.get(
                "range_start",
                "",
            ).strip()
            or None
        )

        end_interface = (
            request.form.get(
                "range_end",
                "",
            ).strip()
            or None
        )

        selected = combine_interface_selection(
            interfaces=interfaces,
            selected_names=selected_names,
            start_interface=start_interface,
            end_interface=end_interface,
        )

        config = parse_interface_configuration()

        has_switchport_config = (
            config["access_vlan"] is not None
            or config["voice_vlan"] is not None
            or config["remove_voice_vlan"]
            or config["portfast_state"] is not None
        )

        if has_switchport_config:
            for item in selected:
                validate_switchport_change(
                    interfaces=interfaces,
                    interface=item["name"],
                    access_vlan=config["access_vlan"],
                    voice_vlan=config["voice_vlan"],
                    remove_voice_vlan=config["remove_voice_vlan"],
                    portfast_state=config["portfast_state"],
                )

        result = provision_interfaces_batch(
            **switch_credentials(),
            interfaces=[item["name"] for item in selected],
            **config,
        )

        return render_page(
            result=result,
        )

    except Exception as exc:
        return render_page(
            error=str(exc),
        )


@app.post("/configuration/save")
def configuration_save():
    try:
        result = save_running_to_startup(**switch_credentials())

        return render_page(
            config_result={
                "type": "save",
                "success": result["success"],
                "message": ("Configuração salva na NVRAM com sucesso."),
            }
        )

    except Exception as exc:
        return render_page(
            config_error=str(exc),
        )


@app.post("/configuration/backup")
def configuration_create_backup():
    protocol = (
        request.form.get(
            "backup_protocol",
            "local",
        )
        .strip()
        .lower()
    )

    try:
        backup_port = request.form.get("backup_port") or None

        result = create_switch_backup(
            **switch_credentials(),
            protocol=protocol,
            backup_host=request.form.get("backup_host"),
            backup_port=backup_port,
            backup_username=request.form.get("backup_username"),
            backup_password=request.form.get("backup_password"),
            remote_directory=(request.form.get("backup_remote_directory") or "/"),
        )

        return render_page(
            config_result={
                "type": "backup",
                "success": True,
                "backup": result,
            },
        )

    except Exception as exc:
        return render_page(
            config_result={
                "type": "backup",
                "success": False,
                "error": str(exc),
                "protocol": protocol,
            },
        ), 500


@app.get("/configuration/download")
def configuration_download_selected():
    config_type = (
        request.args.get(
            "config_type",
            "running",
        )
        .strip()
        .lower()
    )

    if config_type not in {
        "running",
        "startup",
    }:
        return render_page(
            config_error=("Tipo de configuração inválido."),
        ), 400

    from src.switch.configuration import (
        build_backup_filename,
        extract_hostname,
        normalize_config_text,
    )

    if config_type == "running":
        config = get_running_config(**switch_credentials())
    else:
        config = get_startup_config(**switch_credentials())

    hostname = extract_hostname(config)

    filename = build_backup_filename(
        hostname=hostname,
        config_type=config_type,
    )

    content = normalize_config_text(config).encode("utf-8")

    return send_file(
        BytesIO(content),
        as_attachment=True,
        download_name=filename,
        mimetype=("text/plain; charset=utf-8"),
    )


@app.get("/configuration/download/running")
def configuration_download_running():
    from src.switch.configuration import (
        build_backup_filename,
        extract_hostname,
        normalize_config_text,
    )

    config = get_running_config(**switch_credentials())

    hostname = extract_hostname(config)

    filename = build_backup_filename(
        hostname=hostname,
        config_type="running",
    )

    content = normalize_config_text(config).encode("utf-8")

    return send_file(
        BytesIO(content),
        as_attachment=True,
        download_name=filename,
        mimetype=("text/plain; charset=utf-8"),
    )


@app.get("/configuration/download/startup")
def configuration_download_startup():
    from src.switch.configuration import (
        build_backup_filename,
        extract_hostname,
        normalize_config_text,
    )

    config = get_startup_config(**switch_credentials())

    hostname = extract_hostname(config)

    filename = build_backup_filename(
        hostname=hostname,
        config_type="startup",
    )

    content = normalize_config_text(config).encode("utf-8")

    return send_file(
        BytesIO(content),
        as_attachment=True,
        download_name=filename,
        mimetype=("text/plain; charset=utf-8"),
    )


@app.post("/configuration/diff/live")
def configuration_diff_live():
    try:
        running = get_running_config(**switch_credentials())

        startup = get_startup_config(**switch_credentials())

        diff = compare_config_texts(
            left_text=startup,
            right_text=running,
            left_label="startup-config",
            right_label="running-config",
        )

        return render_page(
            config_result={
                "type": "diff",
                "diff": diff,
            }
        )

    except Exception as exc:
        return render_page(
            config_error=str(exc),
        )


@app.post("/configuration/diff/files")
def configuration_diff_files():
    try:
        from src.switch.configuration import (
            validate_config_filename,
        )

        left_file = request.files.get("diff_left_file")

        right_file = request.files.get("diff_right_file")

        if left_file is None or right_file is None:
            raise ValueError("Selecione os dois arquivos para comparação.")

        validate_config_filename(left_file.filename)

        validate_config_filename(right_file.filename)

        left_text = left_file.read().decode(
            "utf-8",
            errors="replace",
        )

        right_text = right_file.read().decode(
            "utf-8",
            errors="replace",
        )

        diff = compare_config_texts(
            left_text=left_text,
            right_text=right_text,
            left_label=left_file.filename,
            right_label=right_file.filename,
        )

        return render_page(
            config_result={
                "type": "diff",
                "diff": diff,
            }
        )

    except Exception as exc:
        return render_page(
            config_error=str(exc),
        )


@app.get("/api/troubleshooting/interfaces")
def troubleshooting_interfaces():
    try:
        result = get_switch_l3_interfaces(**switch_credentials())

        return jsonify(
            {
                "success": True,
                "interfaces": result["interfaces"],
            }
        )

    except Exception as exc:
        return (
            jsonify(
                {
                    "success": False,
                    "error": str(exc),
                    "interfaces": [],
                }
            ),
            500,
        )


@app.post("/troubleshooting/ping")
def troubleshooting_ping():
    try:
        source_interface = request.form.get(
            "ping_source",
            "",
        ).strip()

        targets = request.form.get(
            "ping_targets",
            "",
        ).strip()

        if not source_interface:
            raise ValueError("Selecione uma interface L3 de origem.")

        def positive_int(field, label, default):
            raw = request.form.get(
                field,
                str(default),
            ).strip()

            try:
                value = int(raw)
            except ValueError as exc:
                raise ValueError(f"{label} deve ser um número inteiro.") from exc

            if value < 1:
                raise ValueError(f"{label} deve ser maior que zero.")

            return value

        repeat = positive_int(
            "ping_repeat",
            "Quantidade de pacotes",
            5,
        )

        timeout = positive_int(
            "ping_timeout",
            "Timeout",
            2,
        )

        size = positive_int(
            "ping_size",
            "Tamanho do pacote",
            100,
        )

        concurrency = positive_int(
            "ping_concurrency",
            "Concorrência",
            4,
        )

        if concurrency > 8:
            raise ValueError("A concorrência máxima permitida é 8.")

        df_bit = request.form.get("ping_df_bit") == "on"

        troubleshooting_result = {
            "type": "ping",
            **run_switch_ping(
                **switch_credentials(),
                source_interface=source_interface,
                targets=targets,
                repeat=repeat,
                timeout=timeout,
                size=size,
                df_bit=df_bit,
                concurrency=concurrency,
            ),
        }

        return render_page(
            troubleshooting_result=troubleshooting_result,
        )

    except Exception as exc:
        return render_page(
            troubleshooting_error=str(exc),
        )


@app.post("/troubleshooting/traceroute")
def troubleshooting_traceroute():
    try:
        source_interface = request.form.get(
            "trace_source",
            "",
        ).strip()

        destination = request.form.get(
            "trace_destination",
            "",
        ).strip()

        if not source_interface:
            raise ValueError("Selecione uma interface L3 de origem.")

        def positive_int(field, label, default):
            raw = request.form.get(
                field,
                str(default),
            ).strip()

            try:
                value = int(raw)
            except ValueError as exc:
                raise ValueError(f"{label} deve ser um número inteiro.") from exc

            if value < 1:
                raise ValueError(f"{label} deve ser maior que zero.")

            return value

        timeout = positive_int(
            "trace_timeout",
            "Timeout",
            1,
        )

        probe_count = positive_int(
            "trace_probe_count",
            "Probes por salto",
            3,
        )

        max_ttl = positive_int(
            "trace_max_ttl",
            "TTL máximo",
            20,
        )

        troubleshooting_result = {
            "type": "traceroute",
            **run_switch_traceroute(
                **switch_credentials(),
                source_interface=source_interface,
                destination=destination,
                timeout=timeout,
                probe_count=probe_count,
                max_ttl=max_ttl,
            ),
        }

        return render_page(
            troubleshooting_result=troubleshooting_result,
        )

    except Exception as exc:
        return render_page(
            troubleshooting_error=str(exc),
        )


# Mantido para compatibilidade com testes e histórico
# do incremento anterior. Não é mais usado pela UX.
@app.post("/batch-preview")
def batch_preview():
    (
        interfaces,
        vlan_state,
        capabilities,
        inventory_error,
    ) = load_inventory()

    try:
        if inventory_error:
            raise ValueError(
                f"Não foi possível consultar as interfaces do switch: {inventory_error}"
            )

        selected_names = request.form.getlist("batch_interfaces")

        start_interface = (
            request.form.get(
                "batch_start_interface",
                "",
            ).strip()
            or None
        )

        end_interface = (
            request.form.get(
                "batch_end_interface",
                "",
            ).strip()
            or None
        )

        preview = build_selection_preview(
            interfaces=interfaces,
            selected_names=selected_names,
            start_interface=start_interface,
            end_interface=end_interface,
        )

        config = parse_interface_configuration(prefix="batch_")

        desired_changes = []

        if config["description"]:
            desired_changes.append(f"Description: {config['description']}")

        if config["remove_description"]:
            desired_changes.append("Remover Description")

        if config["access_vlan"] is not None:
            desired_changes.append(f"Access VLAN: {config['access_vlan']}")

        if config["voice_vlan"] is not None:
            desired_changes.append(f"Voice VLAN: {config['voice_vlan']}")

        if config["remove_voice_vlan"]:
            desired_changes.append("Remover Voice VLAN")

        if config["admin_state"] == "up":
            desired_changes.append("Estado administrativo: Admin Up")

        if config["admin_state"] == "down":
            desired_changes.append("Estado administrativo: Admin Down")

        if config["portfast_state"] == "enable":
            desired_changes.append("PortFast: habilitar Edge")

        if config["portfast_state"] == "disable":
            desired_changes.append("PortFast: desabilitar")

        preview["desired_changes"] = desired_changes

        preview["form"] = {
            "selected_names": selected_names,
            "start_interface": start_interface,
            "end_interface": end_interface,
            **config,
        }

        return render_template(
            "index.html",
            result=None,
            error=None,
            interfaces=interfaces,
            vlan_state=vlan_state,
            inventory_error=inventory_error,
            capabilities=capabilities,
            batch_preview=preview,
        )

    except Exception as exc:
        return render_template(
            "index.html",
            result=None,
            error=str(exc),
            interfaces=interfaces,
            vlan_state=vlan_state,
            inventory_error=inventory_error,
            capabilities=capabilities,
            batch_preview=None,
        )


# Compatibilidade com os testes e chamadas anteriores.
@app.post("/apply")
def apply_configuration():
    interfaces, _, capabilities, inventory_error = load_inventory()

    try:
        if inventory_error:
            raise ValueError(
                f"Não foi possível consultar as interfaces do switch: {inventory_error}"
            )

        hostname = (
            request.form.get(
                "hostname",
                "",
            ).strip()
            or None
        )

        vlans = parse_vlans()

        interface = (
            request.form.get(
                "interface",
                "",
            ).strip()
            or None
        )

        config = parse_interface_configuration()

        if interface:
            valid_interfaces = {item["name"] for item in interfaces}

            if interface not in valid_interfaces:
                raise ValueError(
                    f"A interface {interface} não foi encontrada no switch."
                )

            validate_switchport_change(
                interfaces=interfaces,
                interface=interface,
                access_vlan=config["access_vlan"],
                voice_vlan=config["voice_vlan"],
                remove_voice_vlan=config["remove_voice_vlan"],
            )

        legacy_config = {
            key: value for key, value in config.items() if key != "portfast_state"
        }

        result = provision_switch(
            **switch_credentials(),
            hostname=hostname,
            vlans=vlans,
            interface=interface,
            **legacy_config,
        )

        return render_page(
            result=result,
        )

    except Exception as exc:
        return render_page(
            error=str(exc),
        )


@app.post("/api/provision/candidates/<candidate_id>/deploy")
def api_provision_candidate_deploy(
    candidate_id,
):
    candidate = _provision_candidates.get(candidate_id)

    if candidate is None:
        return jsonify(
            {
                "success": False,
                "error": ("Candidate não encontrado."),
            }
        ), 404

    device_id = candidate.get("device_id")

    if not device_id:
        return jsonify(
            {
                "success": False,
                "error": ("Candidate sem equipamento associado."),
            }
        ), 400

    try:
        device = device_manager.get(device_id)

    except KeyError:
        return jsonify(
            {
                "success": False,
                "error": ("Equipamento do Candidate não encontrado."),
            }
        ), 404

    config_text = str(
        candidate.get(
            "config",
            "",
        )
        or ""
    )

    if not config_text.strip():
        return jsonify(
            {
                "success": False,
                "error": ("Candidate sem configuração para aplicar."),
            }
        ), 400

    try:
        result = deploy_candidate_config(
            **device.credentials(),
            config_text=config_text,
        )

    except (
        RuntimeError,
        ValueError,
    ) as exc:
        return jsonify(
            {
                "success": False,
                "error": ("Deploy falhou: " + str(exc)),
            }
        ), 400

    except Exception as exc:
        return jsonify(
            {
                "success": False,
                "error": ("Falha inesperada no deploy: " + str(exc)),
            }
        ), 500

    candidate["running_config_after_deploy"] = result.get(
        "running_config",
        "",
    )

    candidate["deploy_result"] = {
        "success": result.get(
            "success",
            False,
        ),
        "blocks_sent": result.get(
            "blocks_sent",
            0,
        ),
        "commands_sent": result.get(
            "commands_sent",
            0,
        ),
        "saved": result.get(
            "saved",
            False,
        ),
    }

    return jsonify(
        {
            "success": True,
            "candidate_id": candidate_id,
            "blocks_sent": result.get(
                "blocks_sent",
                0,
            ),
            "commands_sent": result.get(
                "commands_sent",
                0,
            ),
            "saved": result.get(
                "saved",
                False,
            ),
            "message": ("Candidate aplicado na running-config."),
        }
    )


if __name__ == "__main__":
    device_manager.enable_persistence(
        database_path=".runtime/devices.sqlite3",
        key_path=".runtime/device-manager.key",
    )

    fortigate_manager.enable_persistence(
        database_path=".runtime/fortigates.sqlite3",
        key_path=".runtime/fortigates.key",
    )
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
    )
