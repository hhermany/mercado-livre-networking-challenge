import os

from dotenv import load_dotenv
from flask import Flask, render_template, request

from src.switch.service import provision_switch

load_dotenv(".env")

app = Flask(__name__)


@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    error = None

    if request.method == "POST":
        try:
            hostname = request.form["hostname"].strip()

            vlans = [
                (int(request.form["vlan10_id"]), request.form["vlan10_name"].strip()),
                (int(request.form["vlan20_id"]), request.form["vlan20_name"].strip()),
                (int(request.form["vlan50_id"]), request.form["vlan50_name"].strip()),
            ]

            result = provision_switch(
                host=os.environ["SWITCH_HOST"],
                username=os.environ["SWITCH_USERNAME"],
                password=os.environ["SWITCH_PASSWORD"],
                secret=os.getenv("SWITCH_SECRET", ""),
                hostname=hostname,
                vlans=vlans,
            )

        except Exception as exc:
            error = str(exc)

    return render_template(
        "index.html",
        result=result,
        error=error,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
