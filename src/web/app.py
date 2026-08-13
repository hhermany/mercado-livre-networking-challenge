import os

from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, url_for

from src.switch.service import provision_switch

load_dotenv(".env")

app = Flask(__name__)


@app.get("/")
def index():
    return render_template(
        "index.html",
        result=None,
        error=None,
    )


@app.post("/")
def stale_root_post():
    return redirect(url_for("index"))


@app.post("/apply")
def apply_configuration():
    try:
        hostname = request.form.get("hostname", "").strip() or None

        vlans = []

        for row in ("1", "2", "3"):
            vlan_id = request.form.get(f"vlan{row}_id", "").strip()
            vlan_name = request.form.get(f"vlan{row}_name", "").strip()

            if not vlan_id and not vlan_name:
                continue

            if not vlan_id or not vlan_name:
                raise ValueError(
                    "Para configurar uma VLAN, informe ID e nome."
                )

            vlans.append((int(vlan_id), vlan_name))

        result = provision_switch(
            host=os.environ["SWITCH_HOST"],
            username=os.environ["SWITCH_USERNAME"],
            password=os.environ["SWITCH_PASSWORD"],
            secret=os.getenv("SWITCH_SECRET", ""),
            hostname=hostname,
            vlans=vlans,
        )

        return render_template(
            "index.html",
            result=result,
            error=None,
        )

    except Exception as exc:
        return render_template(
            "index.html",
            result=None,
            error=str(exc),
        )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
