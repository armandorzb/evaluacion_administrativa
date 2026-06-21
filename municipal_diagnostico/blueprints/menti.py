from __future__ import annotations

from flask import Blueprint, current_app, redirect, render_template

from municipal_diagnostico.decorators import live_role_required


bp = Blueprint("menti", __name__, url_prefix="/menti")


@bp.route("/")
@live_role_required("administrador", "consulta")
def index():
    public_url = current_app.config.get("MENTI_PUBLIC_URL")
    if public_url:
        return redirect(public_url)
    return render_template("menti/index.html")
