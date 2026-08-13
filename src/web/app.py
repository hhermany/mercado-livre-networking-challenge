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
    # Compatibilidade com formulario antigo/cacheado.
    # Nunca executa configuracao pela raiz.
    return redirect(url_for("index"))


@app.post("/apply")
def apply_configuration():
    try:
        hostname = request.form["hostname"].strip()

        vlans = [
            (
                int(request.form["vlan10_id"]),
                request.form["vlan10_name"].strip(),
            ),
            (
                int(request.form["vlan20_id"]),
                request.form["vlan20_name"].strip(),
            ),
            (
                int(request.form["vlan50_id"]),
                request.form["vlan50_name"].strip(),
            ),
        ]

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
