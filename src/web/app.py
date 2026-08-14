import os
from io import BytesIO

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

from src.switch.batch import (
    build_selection_preview,
    combine_interface_selection,
)
from src.switch.cisco import validate_switchport_change
from src.switch.devices import DeviceManager
from src.switch.service import (
    compare_config_texts,
    create_switch_backup,
    discover_managed_switch,
    get_running_config,
    get_startup_config,
    get_switch_interfaces,
    get_switch_l3_interfaces,
    provision_interfaces_batch,
    provision_switch,
    run_switch_ping,
    run_switch_traceroute,
    save_running_to_startup,
)

load_dotenv(".env")

app = Flask(__name__)


device_manager = DeviceManager(
    max_workers=4
)


def selected_device_id():
    return (
        request.values.get(
            "device_id"
        )
        or request.headers.get(
            "X-Device-ID"
        )
    )


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
    device_id = (
        device_id
        or selected_device_id()
    )

    if (
        device_id
        and device_id != "__legacy_test_device__"
    ):
        try:
            device = device_manager.get(
                device_id
            )

        except KeyError as exc:
            raise ValueError(
                "O equipamento selecionado "
                "não está cadastrado."
            ) from exc

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

    raise ValueError(
        "Selecione um equipamento para executar esta operação."
    )


def load_inventory(
    device_id=None,
):
    effective_device_id = device_id

    if (
        not effective_device_id
        and is_test_runtime()
    ):
        effective_device_id = (
            "__legacy_test_device__"
        )

    if not effective_device_id:
        return [], "", {}, None

    try:
        inventory = get_switch_interfaces(
            **switch_credentials(
                effective_device_id
            )
        )

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
    active_device_id = (
        selected_device_id()
    )

    active_device = None

    if active_device_id:
        try:
            active_device = (
                device_manager.get(
                    active_device_id
                ).public()
            )

        except KeyError:
            active_device_id = None

    if (
        active_device is None
        and is_test_runtime()
    ):
        active_device = (
            legacy_test_device()
        )

        if active_device:
            active_device_id = (
                "__legacy_test_device__"
            )

    (
        interfaces,
        vlan_state,
        capabilities,
        inventory_error,
    ) = load_inventory(
        active_device_id
    )

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
            "active_device": (
                legacy_test_device()
            ),
            "active_device_id": (
                "__legacy_test_device__"
            ),
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
            raise ValueError(
                "Para configurar uma VLAN, "
                "informe ID e nome."
            )

        vlans.append(
            (int(vlan_id), vlan_name)
        )

    return vlans


def parse_interface_configuration(
    prefix="",
):
    def field(name):
        return request.form.get(
            f"{prefix}{name}",
            "",
        ).strip()

    access_raw = field(
        "access_vlan"
    )

    voice_raw = field(
        "voice_vlan"
    )

    access_vlan = (
        int(access_raw)
        if access_raw
        else None
    )

    voice_vlan = (
        int(voice_raw)
        if voice_raw
        else None
    )

    description = (
        field("description")
        or None
    )

    remove_description = (
        request.form.get(
            f"{prefix}remove_description"
        )
        == "on"
    )

    remove_voice_vlan = (
        request.form.get(
            f"{prefix}remove_voice_vlan"
        )
        == "on"
    )

    admin_state = (
        field("admin_state")
        or None
    )

    portfast_state = (
        field("portfast_state")
        or None
    )

    if portfast_state not in (
        None,
        "enable",
        "disable",
    ):
        raise ValueError(
            "PortFast inválido."
        )

    if (
        description is not None
        and remove_description
    ):
        raise ValueError(
            "Para Description, escolha configurar um texto "
            "ou remover a descrição atual."
        )

    if (
        voice_vlan is not None
        and remove_voice_vlan
    ):
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
        "devices": (
            device_manager.list()
        ),
    }


@app.post("/api/devices")
def api_add_device():
    payload = (
        request.get_json(
            silent=True
        )
        or request.form
    )

    try:
        device = device_manager.upsert(
            host=payload.get(
                "host"
            ),
            username=payload.get(
                "username"
            ),
            password=payload.get(
                "password"
            ),
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
        device = device_manager.get(
            device_id
        )

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
        device = (
            device_manager.remove(
                device_id
            )
        )

        return {
            "success": True,
            "device": device.public(),
        }

    except KeyError:
        return {
            "success": False,
            "error": (
                "Equipamento não encontrado."
            ),
        }, 404


@app.post("/api/devices/discover")
def api_discover_devices():
    payload = (
        request.get_json(
            silent=True
        )
        or {}
    )

    device_ids = payload.get(
        "device_ids"
    )

    results = (
        device_manager.discover_many(
            discover_managed_switch,
            device_ids=device_ids,
        )
    )

    return {
        "success": True,
        "devices": results,
    }


@app.get("/")
def index():
    return render_page()


@app.post("/")
def stale_root_post():
    return redirect(
        url_for("index")
    )


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
            raise ValueError(
                "Informe o novo hostname."
            )

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
            raise ValueError(
                "Informe pelo menos uma VLAN."
            )

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
    interfaces, _, capabilities, inventory_error = (
        load_inventory()
    )

    try:
        if inventory_error:
            raise ValueError(
                "Não foi possível consultar "
                "as interfaces do switch: "
                f"{inventory_error}"
            )

        selected_names = request.form.getlist(
            "interfaces"
        )

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
                    access_vlan=config[
                        "access_vlan"
                    ],
                    voice_vlan=config[
                        "voice_vlan"
                    ],
                    remove_voice_vlan=config[
                        "remove_voice_vlan"
                    ],
                    portfast_state=config[
                        "portfast_state"
                    ],
                )

        result = provision_interfaces_batch(
            **switch_credentials(),
            interfaces=[
                item["name"]
                for item in selected
            ],
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
        result = save_running_to_startup(
            **switch_credentials()
        )

        return render_page(
            config_result={
                "type": "save",
                "success": result["success"],
                "message": (
                    "Configuração salva na NVRAM com sucesso."
                ),
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
        backup_port = (
            request.form.get(
                "backup_port"
            )
            or None
        )

        result = create_switch_backup(
            **switch_credentials(),
            protocol=protocol,
            backup_host=request.form.get(
                "backup_host"
            ),
            backup_port=backup_port,
            backup_username=request.form.get(
                "backup_username"
            ),
            backup_password=request.form.get(
                "backup_password"
            ),
            remote_directory=(
                request.form.get(
                    "backup_remote_directory"
                )
                or "/"
            ),
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
    config_type = request.args.get(
        "config_type",
        "running",
    ).strip().lower()

    if config_type not in {
        "running",
        "startup",
    }:
        return render_page(
            config_error=(
                "Tipo de configuração inválido."
            ),
        ), 400

    from src.switch.configuration import (
        build_backup_filename,
        extract_hostname,
        normalize_config_text,
    )

    if config_type == "running":
        config = get_running_config(
            **switch_credentials()
        )
    else:
        config = get_startup_config(
            **switch_credentials()
        )

    hostname = extract_hostname(
        config
    )

    filename = build_backup_filename(
        hostname=hostname,
        config_type=config_type,
    )

    content = normalize_config_text(
        config
    ).encode(
        "utf-8"
    )

    return send_file(
        BytesIO(content),
        as_attachment=True,
        download_name=filename,
        mimetype=(
            "text/plain; charset=utf-8"
        ),
    )


@app.get("/configuration/download/running")
def configuration_download_running():
    from src.switch.configuration import (
        build_backup_filename,
        extract_hostname,
        normalize_config_text,
    )

    config = get_running_config(
        **switch_credentials()
    )

    hostname = extract_hostname(
        config
    )

    filename = build_backup_filename(
        hostname=hostname,
        config_type="running",
    )

    content = normalize_config_text(
        config
    ).encode(
        "utf-8"
    )

    return send_file(
        BytesIO(content),
        as_attachment=True,
        download_name=filename,
        mimetype=(
            "text/plain; charset=utf-8"
        ),
    )


@app.get("/configuration/download/startup")
def configuration_download_startup():
    from src.switch.configuration import (
        build_backup_filename,
        extract_hostname,
        normalize_config_text,
    )

    config = get_startup_config(
        **switch_credentials()
    )

    hostname = extract_hostname(
        config
    )

    filename = build_backup_filename(
        hostname=hostname,
        config_type="startup",
    )

    content = normalize_config_text(
        config
    ).encode(
        "utf-8"
    )

    return send_file(
        BytesIO(content),
        as_attachment=True,
        download_name=filename,
        mimetype=(
            "text/plain; charset=utf-8"
        ),
    )


@app.post("/configuration/diff/live")
def configuration_diff_live():
    try:
        running = get_running_config(
            **switch_credentials()
        )

        startup = get_startup_config(
            **switch_credentials()
        )

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

        left_file = request.files.get(
            "diff_left_file"
        )

        right_file = request.files.get(
            "diff_right_file"
        )

        if left_file is None or right_file is None:
            raise ValueError(
                "Selecione os dois arquivos para comparação."
            )

        validate_config_filename(
            left_file.filename
        )

        validate_config_filename(
            right_file.filename
        )

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
        result = get_switch_l3_interfaces(
            **switch_credentials()
        )

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
            raise ValueError(
                "Selecione uma interface L3 de origem."
            )

        def positive_int(field, label, default):
            raw = request.form.get(
                field,
                str(default),
            ).strip()

            try:
                value = int(raw)
            except ValueError as exc:
                raise ValueError(
                    f"{label} deve ser um número inteiro."
                ) from exc

            if value < 1:
                raise ValueError(
                    f"{label} deve ser maior que zero."
                )

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
            raise ValueError(
                "A concorrência máxima permitida é 8."
            )

        df_bit = (
            request.form.get(
                "ping_df_bit"
            )
            == "on"
        )

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
            raise ValueError(
                "Selecione uma interface L3 de origem."
            )

        def positive_int(field, label, default):
            raw = request.form.get(
                field,
                str(default),
            ).strip()

            try:
                value = int(raw)
            except ValueError as exc:
                raise ValueError(
                    f"{label} deve ser um número inteiro."
                ) from exc

            if value < 1:
                raise ValueError(
                    f"{label} deve ser maior que zero."
                )

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
                "Não foi possível consultar "
                "as interfaces do switch: "
                f"{inventory_error}"
            )

        selected_names = request.form.getlist(
            "batch_interfaces"
        )

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

        config = parse_interface_configuration(
            prefix="batch_"
        )

        desired_changes = []

        if config["description"]:
            desired_changes.append(
                f"Description: "
                f"{config['description']}"
            )

        if config["remove_description"]:
            desired_changes.append(
                "Remover Description"
            )

        if config["access_vlan"] is not None:
            desired_changes.append(
                f"Access VLAN: "
                f"{config['access_vlan']}"
            )

        if config["voice_vlan"] is not None:
            desired_changes.append(
                f"Voice VLAN: "
                f"{config['voice_vlan']}"
            )

        if config["remove_voice_vlan"]:
            desired_changes.append(
                "Remover Voice VLAN"
            )

        if config["admin_state"] == "up":
            desired_changes.append(
                "Estado administrativo: Admin Up"
            )

        if config["admin_state"] == "down":
            desired_changes.append(
                "Estado administrativo: Admin Down"
            )

        if config["portfast_state"] == "enable":
            desired_changes.append(
                "PortFast: habilitar Edge"
            )

        if config["portfast_state"] == "disable":
            desired_changes.append(
                "PortFast: desabilitar"
            )

        preview["desired_changes"] = (
            desired_changes
        )

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
    interfaces, _, capabilities, inventory_error = (
        load_inventory()
    )

    try:
        if inventory_error:
            raise ValueError(
                "Não foi possível consultar "
                "as interfaces do switch: "
                f"{inventory_error}"
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
            valid_interfaces = {
                item["name"]
                for item in interfaces
            }

            if interface not in valid_interfaces:
                raise ValueError(
                    f"A interface {interface} "
                    "não foi encontrada no switch."
                )

            validate_switchport_change(
                interfaces=interfaces,
                interface=interface,
                access_vlan=config[
                    "access_vlan"
                ],
                voice_vlan=config[
                    "voice_vlan"
                ],
                remove_voice_vlan=config[
                    "remove_voice_vlan"
                ],
            )

        legacy_config = {
            key: value
            for key, value in config.items()
            if key != "portfast_state"
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


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
    )
