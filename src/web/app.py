import os

from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, url_for

from src.switch.batch import build_selection_preview
from src.switch.cisco import validate_switchport_change
from src.switch.service import get_switch_interfaces, provision_switch

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


@app.get("/")
def index():
    interfaces, vlan_state, inventory_error = load_inventory()

    return render_template(
        "index.html",
        result=None,
        error=None,
        interfaces=interfaces,
        vlan_state=vlan_state,
        inventory_error=inventory_error,
        batch_preview=None,
    )


@app.post("/")
def stale_root_post():
    return redirect(url_for("index"))


@app.post("/batch-preview")
def batch_preview():
    interfaces, vlan_state, inventory_error = load_inventory()

    try:
        if inventory_error:
            raise ValueError(
                "Não foi possível consultar as interfaces do switch: "
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

        access_vlan_raw = request.form.get(
            "batch_access_vlan",
            "",
        ).strip()

        voice_vlan_raw = request.form.get(
            "batch_voice_vlan",
            "",
        ).strip()

        access_vlan = (
            int(access_vlan_raw)
            if access_vlan_raw
            else None
        )

        voice_vlan = (
            int(voice_vlan_raw)
            if voice_vlan_raw
            else None
        )

        description = (
            request.form.get(
                "batch_description",
                "",
            ).strip()
            or None
        )

        remove_description = (
            request.form.get(
                "batch_remove_description"
            )
            == "on"
        )

        remove_voice_vlan = (
            request.form.get(
                "batch_remove_voice_vlan"
            )
            == "on"
        )

        admin_state = (
            request.form.get(
                "batch_admin_state",
                "",
            ).strip()
            or None
        )

        if description is not None and remove_description:
            raise ValueError(
                "Para Description em lote, escolha configurar "
                "um texto ou remover a descrição."
            )

        if voice_vlan is not None and remove_voice_vlan:
            raise ValueError(
                "Para Voice VLAN em lote, escolha configurar "
                "uma VLAN ou remover a Voice VLAN."
            )

        if admin_state not in (
            None,
            "up",
            "down",
        ):
            raise ValueError(
                "Estado administrativo inválido."
            )

        preview = build_selection_preview(
            interfaces=interfaces,
            selected_names=selected_names,
            start_interface=start_interface,
            end_interface=end_interface,
        )

        desired_changes = []

        if description is not None:
            desired_changes.append(
                f"Description: {description}"
            )

        if remove_description:
            desired_changes.append(
                "Remover Description"
            )

        if access_vlan is not None:
            desired_changes.append(
                f"Access VLAN: {access_vlan}"
            )

        if voice_vlan is not None:
            desired_changes.append(
                f"Voice VLAN: {voice_vlan}"
            )

        if remove_voice_vlan:
            desired_changes.append(
                "Remover Voice VLAN"
            )

        if admin_state == "up":
            desired_changes.append(
                "Estado administrativo: Admin Up"
            )

        if admin_state == "down":
            desired_changes.append(
                "Estado administrativo: Admin Down"
            )

        preview["desired_changes"] = desired_changes

        preview["form"] = {
            "selected_names": selected_names,
            "start_interface": start_interface,
            "end_interface": end_interface,
            "description": description,
            "remove_description": remove_description,
            "access_vlan": access_vlan,
            "voice_vlan": voice_vlan,
            "remove_voice_vlan": remove_voice_vlan,
            "admin_state": admin_state,
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


@app.post("/apply")
def apply_configuration():
    interfaces, vlan_state, inventory_error = load_inventory()

    try:
        if inventory_error:
            raise ValueError(
                "Não foi possível consultar as interfaces do switch: "
                f"{inventory_error}"
            )

        hostname = (
            request.form.get("hostname", "").strip()
            or None
        )

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
                    "Para configurar uma VLAN, informe ID e nome."
                )

            vlans.append(
                (int(vlan_id), vlan_name)
            )

        interface = (
            request.form.get("interface", "").strip()
            or None
        )

        access_vlan_raw = request.form.get(
            "access_vlan",
            "",
        ).strip()

        voice_vlan_raw = request.form.get(
            "voice_vlan",
            "",
        ).strip()

        access_vlan = (
            int(access_vlan_raw)
            if access_vlan_raw
            else None
        )

        voice_vlan = (
            int(voice_vlan_raw)
            if voice_vlan_raw
            else None
        )

        remove_voice_vlan = (
            request.form.get("remove_voice_vlan")
            == "on"
        )

        description = (
            request.form.get(
                "description",
                "",
            ).strip()
            or None
        )

        remove_description = (
            request.form.get("remove_description")
            == "on"
        )

        admin_state = (
            request.form.get(
                "admin_state",
                "",
            ).strip()
            or None
        )

        if voice_vlan is not None and remove_voice_vlan:
            raise ValueError(
                "Para Voice VLAN, escolha configurar um número "
                "ou remover a configuração atual."
            )

        if description is not None and remove_description:
            raise ValueError(
                "Para Description, escolha configurar um texto "
                "ou remover a descrição atual."
            )

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
                access_vlan=access_vlan,
                voice_vlan=voice_vlan,
                remove_voice_vlan=remove_voice_vlan,
            )

        result = provision_switch(
            **switch_credentials(),
            hostname=hostname,
            vlans=vlans,
            interface=interface,
            access_vlan=access_vlan,
            voice_vlan=voice_vlan,
            remove_voice_vlan=remove_voice_vlan,
            description=description,
            remove_description=remove_description,
            admin_state=admin_state,
        )

        interfaces, vlan_state, inventory_error = load_inventory()

        return render_template(
            "index.html",
            result=result,
            error=None,
            interfaces=interfaces,
            vlan_state=vlan_state,
            inventory_error=inventory_error,
            batch_preview=None,
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


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
    )
