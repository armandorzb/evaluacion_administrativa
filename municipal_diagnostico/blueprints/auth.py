from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from municipal_diagnostico.extensions import db
from municipal_diagnostico.models import Usuario
from municipal_diagnostico.services.activity_logger import close_platform_session, log_activity, open_platform_session


bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.home"))

    if request.method == "POST":
        email = request.form.get("correo", "").strip().lower()
        password = request.form.get("password", "")
        user = Usuario.query.filter_by(correo=email, activo=True).first()
        if user and user.check_password(password):
            if not user.modulos_disponibles:
                flash("Tu cuenta no tiene módulos asignados. Solicita acceso a un administrador.", "error")
                log_activity(
                    "login_denied_no_modules",
                    entity_type="usuario",
                    entity_id=user.id,
                    metadata={"rol": user.rol},
                )
                return render_template("auth/login.html", admin_exists=Usuario.query.filter_by(rol="administrador").first() is not None)
            login_user(user)
            open_platform_session(user)
            log_activity(
                "login_success",
                entity_type="usuario",
                entity_id=user.id,
                metadata={"rol": user.rol},
            )
            return redirect(url_for("dashboard.home"))
        flash("Credenciales incorrectas o usuario inactivo.", "error")

    admin_exists = Usuario.query.filter_by(rol="administrador").first() is not None
    return render_template("auth/login.html", admin_exists=admin_exists)


@bp.route("/bootstrap", methods=["GET", "POST"])
def bootstrap():
    if Usuario.query.filter_by(rol="administrador").first():
        flash("Ya existe un administrador inicial.", "error")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        correo = request.form.get("correo", "").strip().lower()
        password = request.form.get("password", "")
        confirmacion = request.form.get("confirmacion", "")

        if not nombre or not correo or not password:
            flash("Completa todos los campos.", "error")
            return render_template("auth/bootstrap.html")
        if password != confirmacion:
            flash("Las contraseñas no coinciden.", "error")
            return render_template("auth/bootstrap.html")
        if Usuario.query.filter_by(correo=correo).first():
            flash("Ese correo ya está registrado.", "error")
            return render_template("auth/bootstrap.html")

        user = Usuario(
            nombre=nombre,
            correo=correo,
            rol="administrador",
            activo=True,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash("Administrador inicial creado. Ya puedes iniciar sesión.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/bootstrap.html")


@bp.route("/logout")
@login_required
def logout():
    log_activity("logout", entity_type="usuario", entity_id=current_user.id, commit=False)
    close_platform_session()
    db.session.commit()
    logout_user()
    return redirect(url_for("auth.login"))
