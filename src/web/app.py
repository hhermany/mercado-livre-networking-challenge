import os

from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, url_for

from src.switch.batch import (
    build_selection_preview,
    combine_interface_selection,
)
from src.switch.cisco import validate_switchport_change
from src.switch.service import (
    get_switch_interfaces,
    provision_interfaces_batch,
    provision_switch,
)

load_dotenv(".env")

app = Flask(__name__)


def switch_credentials():
    return {
        "host": os.environ["SWITCH_HOST"],
        "username": os.environ["SWITCH_USERNAME"],
        "password": os.environ["SWITCH_PASSWORD"],
        "secret": os.getenv("SWITCH_SECRET", ""),
    }


def load_inventory():
    try:
        inventory = get_switch_interfaces(
            **switch_credentials()
        )

        return (
            inventory["interfaces"],
            inventory.get("vlan_state", ""),
            None,
        )

    except Exception as exc:
        return [], "", str(exc)


def render_page(
    result=None,
    error=None,
    batch_preview=None,
):
    interfaces, vlan_state, inventory_error = (
        load_inventory()
    )

    return render_template(
        "index.html",
        result=result,
        error=error,
        interfaces=interfaces,
        vlan_state=vlan_state,
        inventory_error=inventory_error,
        batch_preview=batch_preview,
    )


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
    interfaces, _, inventory_error = (
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


# Mantido para compatibilidade com testes e histórico
# do incremento anterior. Não é mais usado pela UX.
@app.post("/batch-preview")
def batch_preview():
    interfaces, vlan_state, inventory_error = (
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
            batch_preview=None,
        )


# Compatibilidade com os testes e chamadas anteriores.
@app.post("/apply")
def apply_configuration():
    interfaces, _, inventory_error = (
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

        result = provision_switch(
            **switch_credentials(),
            hostname=hostname,
            vlans=vlans,
            interface=interface,
            **config,
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
