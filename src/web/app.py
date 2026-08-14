import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from time import perf_counter
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
    load_managed_switch_workspace,
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


@app.post("/api/devices/interfaces/configure")
def api_configure_multi_device_interfaces():
    payload = (
        request.get_json(
            silent=True
        )
        or {}
    )

    selections = payload.get(
        "selections",
        []
    )

    if not isinstance(
        selections,
        list,
    ) or not selections:
        return {
            "success": False,
            "error": (
                "Selecione pelo menos uma interface."
            ),
        }, 400


    access_vlan = payload.get(
        "access_vlan"
    )

    voice_vlan = payload.get(
        "voice_vlan"
    )

    description = payload.get(
        "description"
    )

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

    admin_state = payload.get(
        "admin_state"
    )

    portfast_state = payload.get(
        "portfast_state"
    )


    if (
        access_vlan in ("", None)
    ):
        access_vlan = None
    else:
        try:
            access_vlan = int(
                access_vlan
            )

        except (
            TypeError,
            ValueError,
        ):
            return {
                "success": False,
                "error": (
                    "Access VLAN inválida."
                ),
            }, 400


    if (
        voice_vlan in ("", None)
    ):
        voice_vlan = None
    else:
        try:
            voice_vlan = int(
                voice_vlan
            )

        except (
            TypeError,
            ValueError,
        ):
            return {
                "success": False,
                "error": (
                    "Voice VLAN inválida."
                ),
            }, 400


    if (
        voice_vlan is not None
        and remove_voice_vlan
    ):
        return {
            "success": False,
            "error": (
                "Informe uma Voice VLAN ou "
                "selecione remover, não ambos."
            ),
        }, 400


    if (
        description
        and remove_description
    ):
        return {
            "success": False,
            "error": (
                "Informe uma Description ou "
                "selecione remover, não ambos."
            ),
        }, 400


    if admin_state not in (
        None,
        "",
        "up",
        "down",
    ):
        return {
            "success": False,
            "error": (
                "Estado administrativo inválido."
            ),
        }, 400


    if portfast_state not in (
        None,
        "",
        "enable",
        "disable",
    ):
        return {
            "success": False,
            "error": (
                "Estado de PortFast inválido."
            ),
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
            "error": (
                "Informe pelo menos uma alteração "
                "para aplicar."
            ),
        }, 400


    grouped = {}

    for item in selections:
        device_id = item.get(
            "device_id"
        )

        interface = (
            item.get(
                "interface",
                "",
            )
            or ""
        ).strip()

        if (
            not device_id
            or not interface
        ):
            return {
                "success": False,
                "error": (
                    "Seleção de interface inválida."
                ),
            }, 400

        grouped.setdefault(
            device_id,
            []
        ).append(
            interface
        )


    operation_started = perf_counter()


    def configure_device(
        device_id,
        interfaces,
    ):
        device = device_manager.get(
            device_id
        )

        worker_started = perf_counter()

        result = (
            provision_interfaces_batch(
                **device.credentials(),
                interfaces=interfaces,
                access_vlan=access_vlan,
                voice_vlan=voice_vlan,
                remove_voice_vlan=remove_voice_vlan,
                description=(
                    description
                    if description
                    else None
                ),
                remove_description=remove_description,
                admin_state=(
                    admin_state
                    if admin_state
                    else None
                ),
                portfast_state=(
                    portfast_state
                    if portfast_state
                    else None
                ),
            )
        )

        worker_finished = perf_counter()

        return {
            "device": device.public(),
            "interfaces": interfaces,
            "result": result,
            "timing": {
                "started_ms": round(
                    (
                        worker_started
                        - operation_started
                    )
                    * 1000,
                    1,
                ),
                "finished_ms": round(
                    (
                        worker_finished
                        - operation_started
                    )
                    * 1000,
                    1,
                ),
                "duration_ms": round(
                    (
                        worker_finished
                        - worker_started
                    )
                    * 1000,
                    1,
                ),
            },
        }


    workers = min(
        8,
        len(grouped),
    )

    results = []


    with ThreadPoolExecutor(
        max_workers=workers
    ) as executor:

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
            )
            in grouped.items()
        }


        for future in as_completed(
            futures
        ):
            (
                device_id,
                interfaces,
            ) = futures[
                future
            ]

            try:
                result = future.result()

                service_result = result.get(
                    "result",
                    {}
                )

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
                    device = (
                        device_manager.get(
                            device_id
                        ).public()
                    )

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
        "success": all(
            item["success"]
            for item in results
        ),
        "results": results,
        "timing": {
            "total_ms": round(
                (
                    operation_finished
                    - operation_started
                )
                * 1000,
                1,
            ),
            "workers": workers,
            "devices": len(
                grouped
            ),
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
        raise ValueError(
            "Lista de equipamentos inválida."
        )

    device_ids = [
        str(device_id).strip()
        for device_id in device_ids
        if str(device_id).strip()
    ]

    if not device_ids:
        raise ValueError(
            "Selecione pelo menos um equipamento."
        )

    # Preserva ordem sem duplicatas.
    return list(
        dict.fromkeys(
            device_ids
        )
    )


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
        device = device_manager.get(
            device_id
        )

        worker_started = perf_counter()

        result = operation(
            device
        )

        return {
            "device":
                device.public(),
            "success":
                True,
            "result":
                result,
            "duration_ms":
                round(
                    (
                        perf_counter()
                        - worker_started
                    )
                    * 1000,
                    1,
                ),
        }

    with ThreadPoolExecutor(
        max_workers=workers
    ) as executor:
        futures = {
            executor.submit(
                worker,
                device_id,
            ): device_id
            for device_id
            in device_ids
        }

        for future in as_completed(
            futures
        ):
            device_id = futures[
                future
            ]

            try:
                results.append(
                    future.result()
                )

            except Exception as exc:
                try:
                    device = (
                        device_manager.get(
                            device_id
                        ).public()
                    )

                except Exception:
                    device = {
                        "id":
                            device_id,
                        "hostname":
                            device_id,
                        "host":
                            "",
                    }

                results.append(
                    {
                        "device":
                            device,
                        "success":
                            False,
                        "error":
                            str(exc),
                    }
                )

    results.sort(
        key=lambda item: (
            item.get(
                "device",
                {},
            ).get(
                "host",
                "",
            )
        )
    )

    return {
        "success":
            all(
                item.get(
                    "success",
                    False,
                )
                for item
                in results
            ),
        "results":
            results,
        "timing": {
            "total_ms":
                round(
                    (
                        perf_counter()
                        - operation_started
                    )
                    * 1000,
                    1,
                ),
            "workers":
                workers,
            "devices":
                len(device_ids),
        },
    }


@app.post("/api/devices/configuration/save")
def api_multi_configuration_save():
    payload = (
        request.get_json(
            silent=True
        )
        or {}
    )

    try:
        device_ids = (
            _multi_configuration_device_ids(
                payload
            )
        )

        result = (
            _parallel_configuration_operation(
                device_ids,
                lambda device:
                    save_running_to_startup(
                        **device.credentials()
                    ),
            )
        )

        return jsonify(
            result
        )

    except Exception as exc:
        return jsonify(
            {
                "success":
                    False,
                "error":
                    str(exc),
            }
        ), 400


@app.post("/api/devices/configuration/backup")
def api_multi_configuration_backup():
    payload = (
        request.get_json(
            silent=True
        )
        or {}
    )

    try:
        device_ids = (
            _multi_configuration_device_ids(
                payload
            )
        )

        protocol = str(
            payload.get(
                "protocol",
                "local",
            )
            or "local"
        ).strip().lower()

        if protocol not in {
            "local",
            "ftp",
            "sftp",
            "tftp",
        }:
            raise ValueError(
                "Protocolo de backup inválido."
            )

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

        result = (
            _parallel_configuration_operation(
                device_ids,
                lambda device:
                    create_switch_backup(
                        **device.credentials(),
                        protocol=protocol,
                        backup_host=backup_host,
                        backup_port=backup_port,
                        backup_username=backup_username,
                        backup_password=backup_password,
                        remote_directory=remote_directory,
                    ),
            )
        )

        result["protocol"] = (
            protocol
        )

        return jsonify(
            result
        )

    except Exception as exc:
        return jsonify(
            {
                "success":
                    False,
                "error":
                    str(exc),
            }
        ), 400


@app.post("/api/devices/configuration/download")
def api_multi_configuration_download():
    payload = (
        request.get_json(
            silent=True
        )
        or {}
    )

    try:
        device_ids = (
            _multi_configuration_device_ids(
                payload
            )
        )

        config_type = str(
            payload.get(
                "config_type",
                "running",
            )
            or "running"
        ).strip().lower()

        if config_type not in {
            "running",
            "startup",
        }:
            raise ValueError(
                "Tipo de configuração inválido."
            )

        from src.switch.configuration import (
            build_backup_filename,
            extract_hostname,
            normalize_config_text,
        )

        def collect(
            device,
        ):
            credentials = (
                device.credentials()
            )

            if config_type == "running":
                config = (
                    get_running_config(
                        **credentials
                    )
                )

            else:
                config = (
                    get_startup_config(
                        **credentials
                    )
                )

            hostname = (
                extract_hostname(
                    config
                )
                or device.hostname
                or device.host
            )

            filename = (
                build_backup_filename(
                    hostname=hostname,
                    config_type=config_type,
                )
            )

            return {
                "hostname":
                    hostname,
                "filename":
                    filename,
                "content":
                    normalize_config_text(
                        config
                    ),
            }

        collected = (
            _parallel_configuration_operation(
                device_ids,
                collect,
            )
        )

        failures = [
            item
            for item
            in collected["results"]
            if not item.get(
                "success"
            )
        ]

        if failures:
            return jsonify(
                collected
            ), 500

        files = [
            item["result"]
            for item
            in collected["results"]
        ]

        # Um switch:
        # download direto do .cfg.
        if len(files) == 1:
            item = files[0]

            content = (
                item["content"]
                .encode(
                    "utf-8"
                )
            )

            return send_file(
                BytesIO(
                    content
                ),
                as_attachment=True,
                download_name=(
                    item["filename"]
                ),
                mimetype=(
                    "text/plain; charset=utf-8"
                ),
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
            download_name=(
                f"switches_{config_type}_configs.zip"
            ),
            mimetype="application/zip",
        )

    except Exception as exc:
        return jsonify(
            {
                "success":
                    False,
                "error":
                    str(exc),
            }
        ), 400


@app.post("/api/devices/configuration/diff")
def api_multi_configuration_diff():
    payload = (
        request.get_json(
            silent=True
        )
        or {}
    )

    try:
        device_ids = (
            _multi_configuration_device_ids(
                payload
            )
        )

        def compare(
            device,
        ):
            startup = (
                get_startup_config(
                    **device.credentials()
                )
            )

            running = (
                get_running_config(
                    **device.credentials()
                )
            )

            diff = compare_config_texts(
                left_text=startup,
                right_text=running,
                left_label="startup-config",
                right_label="running-config",
            )

            return {
                "diff":
                    diff,
            }

        result = (
            _parallel_configuration_operation(
                device_ids,
                compare,
            )
        )

        return jsonify(
            result
        )

    except Exception as exc:
        return jsonify(
            {
                "success":
                    False,
                "error":
                    str(exc),
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
        value = int(
            raw
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise ValueError(
            f"{label} deve ser um número inteiro."
        ) from exc

    if value < 1:
        raise ValueError(
            f"{label} deve ser maior que zero."
        )

    if (
        maximum is not None
        and value > maximum
    ):
        raise ValueError(
            f"{label} deve ser no máximo {maximum}."
        )

    return value


def _multi_tshoot_operations(
    payload,
):
    operations = payload.get(
        "operations",
        [],
    )

    if not isinstance(
        operations,
        list,
    ) or not operations:
        raise ValueError(
            "Selecione pelo menos um equipamento."
        )

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
            raise ValueError(
                "Equipamento inválido."
            )

        if not source_interface:
            raise ValueError(
                "Selecione a interface L3 "
                "de origem de cada equipamento."
            )

        if device_id in seen:
            continue

        seen.add(
            device_id
        )

        normalized.append(
            {
                "device_id":
                    device_id,
                "source_interface":
                    source_interface,
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
        device = device_manager.get(
            operation[
                "device_id"
            ]
        )

        worker_started = perf_counter()

        result = callback(
            device,
            operation,
        )

        return {
            "device":
                device.public(),
            "success":
                True,
            "result":
                result,
            "duration_ms":
                round(
                    (
                        perf_counter()
                        - worker_started
                    )
                    * 1000,
                    1,
                ),
        }

    with ThreadPoolExecutor(
        max_workers=workers
    ) as executor:
        futures = {
            executor.submit(
                worker,
                operation,
            ): operation
            for operation
            in operations
        }

        for future in as_completed(
            futures
        ):
            operation = futures[
                future
            ]

            try:
                results.append(
                    future.result()
                )

            except Exception as exc:
                device_id = operation[
                    "device_id"
                ]

                try:
                    device = (
                        device_manager.get(
                            device_id
                        ).public()
                    )

                except Exception:
                    device = {
                        "id":
                            device_id,
                        "hostname":
                            device_id,
                        "host":
                            "",
                    }

                results.append(
                    {
                        "device":
                            device,
                        "success":
                            False,
                        "error":
                            str(exc),
                    }
                )

    results.sort(
        key=lambda item: (
            item.get(
                "device",
                {},
            ).get(
                "host",
                "",
            )
        )
    )

    return {
        "success":
            all(
                item.get(
                    "success",
                    False,
                )
                for item
                in results
            ),
        "results":
            results,
        "timing": {
            "total_ms":
                round(
                    (
                        perf_counter()
                        - started
                    )
                    * 1000,
                    1,
                ),
            "workers":
                workers,
            "devices":
                len(operations),
        },
    }


@app.post("/api/devices/troubleshooting/interfaces")
def api_multi_tshoot_interfaces():
    payload = (
        request.get_json(
            silent=True
        )
        or {}
    )

    device_ids = payload.get(
        "device_ids",
        [],
    )

    if not isinstance(
        device_ids,
        list,
    ) or not device_ids:
        return jsonify(
            {
                "success":
                    False,
                "error":
                    "Selecione pelo menos um equipamento.",
            }
        ), 400

    device_ids = list(
        dict.fromkeys(
            str(item).strip()
            for item in device_ids
            if str(item).strip()
        )
    )

    workers = min(
        device_manager.max_workers,
        len(device_ids),
    )

    results = []

    def worker(
        device_id,
    ):
        device = device_manager.get(
            device_id
        )

        inventory = (
            get_switch_l3_interfaces(
                **device.credentials()
            )
        )

        return {
            "device":
                device.public(),
            "success":
                True,
            "interfaces":
                inventory.get(
                    "interfaces",
                    [],
                ),
        }

    with ThreadPoolExecutor(
        max_workers=workers
    ) as executor:
        futures = {
            executor.submit(
                worker,
                device_id,
            ): device_id
            for device_id
            in device_ids
        }

        for future in as_completed(
            futures
        ):
            device_id = futures[
                future
            ]

            try:
                results.append(
                    future.result()
                )

            except Exception as exc:
                try:
                    device = (
                        device_manager.get(
                            device_id
                        ).public()
                    )

                except Exception:
                    device = {
                        "id":
                            device_id,
                        "hostname":
                            device_id,
                        "host":
                            "",
                    }

                results.append(
                    {
                        "device":
                            device,
                        "success":
                            False,
                        "interfaces":
                            [],
                        "error":
                            str(exc),
                    }
                )

    results.sort(
        key=lambda item: (
            item.get(
                "device",
                {},
            ).get(
                "host",
                "",
            )
        )
    )

    return jsonify(
        {
            "success":
                all(
                    item.get(
                        "success",
                        False,
                    )
                    for item
                    in results
                ),
            "results":
                results,
        }
    )


@app.post("/api/devices/troubleshooting/ping")
def api_multi_tshoot_ping():
    payload = (
        request.get_json(
            silent=True
        )
        or {}
    )

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
            raise ValueError(
                "Selecione pelo menos um equipamento."
            )


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
                raise ValueError(
                    "Equipamento inválido."
                )

            if device_id in seen:
                continue

            seen.add(
                device_id
            )


            if not source_interface:
                raise ValueError(
                    "Selecione uma Source L3 "
                    "para cada equipamento."
                )


            if not targets:
                raise ValueError(
                    "Informe o destino de Ping "
                    "para cada equipamento selecionado."
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
                raise ValueError(
                    "Parâmetros numéricos do Ping são inválidos."
                ) from exc


            if repeat < 1:
                raise ValueError(
                    "Pacotes deve ser maior que zero."
                )

            if timeout < 1:
                raise ValueError(
                    "Timeout deve ser maior que zero."
                )

            if size < 1:
                raise ValueError(
                    "Tamanho deve ser maior que zero."
                )

            if not 1 <= parallelism <= 8:
                raise ValueError(
                    "Paralelismo deve estar entre 1 e 8."
                )


            total_parallelism += (
                parallelism
            )


            operations.append(
                {
                    "device_id":
                        device_id,

                    "source_interface":
                        source_interface,

                    "targets":
                        targets,

                    "repeat":
                        repeat,

                    "timeout":
                        timeout,

                    "size":
                        size,

                    #
                    # O service antigo continua chamando
                    # este parâmetro de concurrency.
                    #
                    "concurrency":
                        parallelism,

                    "df_bit":
                        bool(
                            raw.get(
                                "df_bit",
                                False,
                            )
                        ),
                }
            )


        if total_parallelism > 8:
            raise ValueError(
                "O paralelismo total dos equipamentos "
                "não pode ultrapassar 8."
            )


        result = (
            _parallel_tshoot_operation(
                operations,
                lambda device, operation:
                    run_switch_ping(
                        **device.credentials(),

                        source_interface=(
                            operation[
                                "source_interface"
                            ]
                        ),

                        #
                        # CRÍTICO:
                        # destino pertence à operação/switch.
                        #
                        targets=(
                            operation[
                                "targets"
                            ]
                        ),

                        repeat=(
                            operation[
                                "repeat"
                            ]
                        ),

                        timeout=(
                            operation[
                                "timeout"
                            ]
                        ),

                        size=(
                            operation[
                                "size"
                            ]
                        ),

                        df_bit=(
                            operation[
                                "df_bit"
                            ]
                        ),

                        concurrency=(
                            operation[
                                "concurrency"
                            ]
                        ),
                    ),
            )
        )


        result[
            "total_parallelism"
        ] = total_parallelism


        return jsonify(
            result
        )


    except ValueError as exc:
        return jsonify(
            {
                "success":
                    False,

                "error":
                    str(exc),
            }
        ), 400


    except Exception as exc:
        return jsonify(
            {
                "success":
                    False,

                "error":
                    str(exc),
            }
        ), 500


@app.post("/api/devices/troubleshooting/traceroute")
def api_multi_tshoot_traceroute():
    payload = (
        request.get_json(
            silent=True
        )
        or {}
    )

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
            raise ValueError(
                "Selecione pelo menos um equipamento."
            )


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
                raise ValueError(
                    "Equipamento inválido."
                )


            if device_id in seen:
                continue


            seen.add(
                device_id
            )


            if not source_interface:
                raise ValueError(
                    "Selecione uma Source L3 "
                    "para cada equipamento."
                )


            if not destination:
                raise ValueError(
                    "Informe o destino do Traceroute "
                    "para cada equipamento."
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
                raise ValueError(
                    "Parâmetros do Traceroute inválidos."
                ) from exc


            if timeout < 1:
                raise ValueError(
                    "Timeout deve ser maior que zero."
                )


            if probe_count < 1:
                raise ValueError(
                    "Probes por salto deve ser maior que zero."
                )


            if max_ttl < 1:
                raise ValueError(
                    "TTL máximo deve ser maior que zero."
                )


            operations.append(
                {
                    "device_id":
                        device_id,

                    "source_interface":
                        source_interface,

                    "destination":
                        destination,

                    "timeout":
                        timeout,

                    "probe_count":
                        probe_count,

                    "max_ttl":
                        max_ttl,
                }
            )


        result = (
            _parallel_tshoot_operation(
                operations,
                lambda device, operation:
                    run_switch_traceroute(
                        **device.credentials(),

                        source_interface=(
                            operation[
                                "source_interface"
                            ]
                        ),

                        destination=(
                            operation[
                                "destination"
                            ]
                        ),

                        timeout=(
                            operation[
                                "timeout"
                            ]
                        ),

                        probe_count=(
                            operation[
                                "probe_count"
                            ]
                        ),

                        max_ttl=(
                            operation[
                                "max_ttl"
                            ]
                        ),
                    ),
            )
        )


        return jsonify(
            result
        )


    except ValueError as exc:
        return jsonify(
            {
                "success":
                    False,

                "error":
                    str(exc),
            }
        ), 400


    except Exception as exc:
        return jsonify(
            {
                "success":
                    False,

                "error":
                    str(exc),
            }
        ), 500


@app.post("/api/devices/general/configure")
def api_configure_multi_device_general():
    payload = (
        request.get_json(
            silent=True
        )
        or {}
    )

    operations = payload.get(
        "operations",
        []
    )

    if not isinstance(
        operations,
        list,
    ) or not operations:
        return {
            "success": False,
            "error": (
                "Selecione pelo menos um equipamento."
            ),
        }, 400

    normalized = []

    for operation in operations:
        device_id = operation.get(
            "device_id"
        )

        hostname = (
            operation.get(
                "hostname",
                ""
            )
            or ""
        ).strip() or None

        raw_vlans = operation.get(
            "vlans",
            []
        )

        if not device_id:
            return {
                "success": False,
                "error": (
                    "Equipamento inválido."
                ),
            }, 400

        if not isinstance(
            raw_vlans,
            list,
        ):
            return {
                "success": False,
                "error": (
                    "Lista de VLANs inválida."
                ),
            }, 400

        vlans = []

        for vlan in raw_vlans:
            vlan_id = vlan.get(
                "id"
            )

            vlan_name = (
                vlan.get(
                    "name",
                    ""
                )
                or ""
            ).strip()

            if vlan_id in (
                "",
                None,
            ) and not vlan_name:
                continue

            try:
                vlan_id = int(
                    vlan_id
                )
            except (
                TypeError,
                ValueError,
            ):
                return {
                    "success": False,
                    "error": (
                        "VLAN ID inválida."
                    ),
                }, 400

            if not 1 <= vlan_id <= 4094:
                return {
                    "success": False,
                    "error": (
                        f"VLAN {vlan_id} fora "
                        "do intervalo 1-4094."
                    ),
                }, 400

            if not vlan_name:
                return {
                    "success": False,
                    "error": (
                        f"Informe o nome da VLAN "
                        f"{vlan_id}."
                    ),
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
                    "Informe hostname e/ou VLAN "
                    "para cada equipamento selecionado."
                ),
            }, 400

        normalized.append(
            {
                "device_id":
                    device_id,
                "hostname":
                    hostname,
                "vlans":
                    vlans,
            }
        )

    operation_started = perf_counter()

    def configure_device(
        operation,
    ):
        device = device_manager.get(
            operation[
                "device_id"
            ]
        )

        worker_started = perf_counter()

        result = provision_switch(
            **device.credentials(),
            hostname=operation[
                "hostname"
            ],
            vlans=operation[
                "vlans"
            ],
        )

        if (
            result.get(
                "success"
            )
            and operation[
                "hostname"
            ]
        ):
            device.hostname = (
                operation[
                    "hostname"
                ]
            )

        return {
            "device_id":
                operation[
                    "device_id"
                ],
            "host":
                device.host,
            "hostname":
                (
                    operation[
                        "hostname"
                    ]
                    or device.hostname
                    or device.host
                ),
            "success":
                bool(
                    result.get(
                        "success"
                    )
                ),
            "missing":
                result.get(
                    "missing",
                    [],
                ),
            "changes":
                result.get(
                    "changes",
                    [],
                ),
            "backup":
                result.get(
                    "backup"
                ),
            "duration_ms":
                round(
                    (
                        perf_counter()
                        - worker_started
                    )
                    * 1000,
                    1,
                ),
        }

    workers = min(
        device_manager.max_workers,
        len(
            normalized
        ),
    )

    results = []

    with ThreadPoolExecutor(
        max_workers=workers
    ) as executor:
        futures = {
            executor.submit(
                configure_device,
                operation,
            ): operation
            for operation
            in normalized
        }

        for future in as_completed(
            futures
        ):
            operation = futures[
                future
            ]

            try:
                results.append(
                    future.result()
                )

            except Exception as exc:
                device_id = operation[
                    "device_id"
                ]

                try:
                    device = (
                        device_manager.get(
                            device_id
                        )
                    )

                    host = device.host
                    hostname = (
                        device.hostname
                        or device.host
                    )

                except KeyError:
                    host = ""
                    hostname = device_id

                results.append(
                    {
                        "device_id":
                            device_id,
                        "host":
                            host,
                        "hostname":
                            hostname,
                        "success":
                            False,
                        "missing":
                            [],
                        "changes":
                            [],
                        "error":
                            str(
                                exc
                            ),
                    }
                )

    results.sort(
        key=lambda item: (
            item.get(
                "host",
                ""
            )
        )
    )

    success = all(
        item.get(
            "success"
        )
        for item
        in results
    )

    return {
        "success":
            success,
        "results":
            results,
        "duration_ms":
            round(
                (
                    perf_counter()
                    - operation_started
                )
                * 1000,
                1,
            ),
        "workers":
            workers,
        "devices":
            len(
                normalized
            ),
    }


@app.post("/api/devices/workspace")
def api_devices_workspace():
    payload = (
        request.get_json(
            silent=True
        )
        or {}
    )

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
            "error": (
                "device_ids deve ser uma lista."
            ),
        }, 400

    if not device_ids:
        return {
            "success": False,
            "error": (
                "Selecione pelo menos um equipamento."
            ),
        }, 400

    try:
        results = (
            device_manager.discover_many(
                load_managed_switch_workspace,
                device_ids=device_ids,
            )
        )

    except KeyError:
        return {
            "success": False,
            "error": (
                "Um dos equipamentos selecionados "
                "não está mais cadastrado."
            ),
        }, 404

    return {
        "success": True,
        "devices": results,
    }


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
    device_manager.enable_persistence(
        database_path=".runtime/devices.sqlite3",
        key_path=".runtime/device-manager.key",
    )
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
    )
