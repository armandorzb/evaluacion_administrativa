from __future__ import annotations

import secrets

import click
from flask import current_app
from flask.cli import with_appcontext

from municipal_diagnostico.extensions import db
from municipal_diagnostico.models import (
    Area,
    CuestionarioVersion,
    Dependencia,
    EjeVersion,
    Evaluacion,
    ReactivoVersion,
    Usuario,
)
from municipal_diagnostico.seed_data import OFFICIAL_QUESTIONNAIRE
from municipal_diagnostico.timeutils import utcnow


def create_questionnaire_version(
    *,
    nombre: str,
    descripcion: str,
    creado_por: Usuario | None = None,
    publicar: bool = False,
) -> CuestionarioVersion:
    version = CuestionarioVersion(
        nombre=nombre,
        descripcion=descripcion,
        estado="publicado" if publicar else "borrador",
        publicado_at=utcnow() if publicar else None,
        creado_por=creado_por,
    )
    db.session.add(version)
    db.session.flush()

    for eje_data in OFFICIAL_QUESTIONNAIRE["ejes"]:
        eje = EjeVersion(
            cuestionario_version=version,
            clave=eje_data["clave"],
            orden=eje_data["orden"],
            nombre=eje_data["nombre"],
            descripcion=eje_data["descripcion"],
            ponderacion=eje_data["ponderacion"],
        )
        db.session.add(eje)
        db.session.flush()
        for orden, reactivo_data in enumerate(eje_data["reactivos"], start=1):
            db.session.add(
                ReactivoVersion(
                    eje_version=eje,
                    codigo=reactivo_data["codigo"],
                    orden=orden,
                    pregunta=reactivo_data["pregunta"],
                    opciones=reactivo_data["opciones"],
                )
            )

    return version


def ensure_official_questionnaire() -> CuestionarioVersion:
    version = (
        CuestionarioVersion.query.filter_by(nombre=OFFICIAL_QUESTIONNAIRE["nombre"])
        .order_by(CuestionarioVersion.id.asc())
        .first()
    )
    if version:
        return version

    version = create_questionnaire_version(
        nombre=OFFICIAL_QUESTIONNAIRE["nombre"],
        descripcion=OFFICIAL_QUESTIONNAIRE["descripcion"],
        publicar=True,
    )
    db.session.commit()
    return version


def clone_questionnaire_version(
    source_version: CuestionarioVersion,
    *,
    creado_por: Usuario | None,
    nombre: str | None = None,
    descripcion: str | None = None,
) -> CuestionarioVersion:
    clone = CuestionarioVersion(
        nombre=nombre or f"{source_version.nombre} (borrador)",
        descripcion=descripcion or source_version.descripcion,
        estado="borrador",
        creado_por=creado_por,
    )
    db.session.add(clone)
    db.session.flush()

    for eje in source_version.ejes:
        new_eje = EjeVersion(
            cuestionario_version=clone,
            clave=eje.clave,
            orden=eje.orden,
            nombre=eje.nombre,
            descripcion=eje.descripcion,
            ponderacion=eje.ponderacion,
        )
        db.session.add(new_eje)
        db.session.flush()
        for reactivo in eje.reactivos:
            db.session.add(
                ReactivoVersion(
                    eje_version=new_eje,
                    codigo=reactivo.codigo,
                    orden=reactivo.orden,
                    pregunta=reactivo.pregunta,
                    opciones=reactivo.opciones,
                )
            )
    return clone


def bootstrap_admin(email: str, password: str | None, name: str | None = None) -> Usuario:
    user = Usuario.query.filter_by(correo=email).first()
    if user:
        return user

    generated_password = password or secrets.token_urlsafe(12)
    user = Usuario(
        nombre=name or "Administrador Inicial",
        correo=email,
        rol="administrador",
        activo=True,
    )
    user.set_password(generated_password)
    db.session.add(user)
    db.session.commit()
    current_app.logger.info("Administrador inicial creado: %s", email)
    if not password:
        current_app.logger.warning("Contraseña temporal del administrador inicial: %s", generated_password)
    return user


def seed_sample_catalogs() -> None:
    if Dependencia.query.first():
        return

    oficialia = Dependencia(nombre="Oficialía Mayor", tipo="Administrativa")
    tesoreria = Dependencia(nombre="Tesorería Municipal", tipo="Administrativa")
    db.session.add_all([oficialia, tesoreria])
    db.session.flush()

    db.session.add_all(
        [
            Area(nombre="Recursos Humanos", dependencia=oficialia),
            Area(nombre="Tecnologías de la Información", dependencia=oficialia),
            Area(nombre="Ingresos", dependencia=tesoreria),
        ]
    )
    db.session.commit()


def create_period_evaluations_for_dependencias(periodo) -> None:
    for dependencia in Dependencia.query.filter_by(activa=True).order_by(Dependencia.nombre).all():
        exists = Evaluacion.query.filter_by(periodo_id=periodo.id, dependencia_id=dependencia.id).first()
        if not exists:
            db.session.add(
                Evaluacion(
                    periodo_id=periodo.id,
                    dependencia_id=dependencia.id,
                    estado="borrador",
                )
            )


def register_cli_commands(app) -> None:
    @app.cli.command("init-db")
    @click.option("--with-sample-data", is_flag=True, help="Carga dependencias y áreas base.")
    @with_appcontext
    def init_db_command(with_sample_data: bool) -> None:
        db.create_all()
        ensure_official_questionnaire()
        if with_sample_data:
            seed_sample_catalogs()

        email = current_app.config.get("BOOTSTRAP_ADMIN_EMAIL")
        password = current_app.config.get("BOOTSTRAP_ADMIN_PASSWORD")
        if email:
            bootstrap_admin(email, password, current_app.config.get("BOOTSTRAP_ADMIN_NAME"))

        click.echo("Base de datos inicializada.")

    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    @click.option("--name", default="Administrador")
    @with_appcontext
    def create_admin_command(email: str, password: str, name: str) -> None:
        bootstrap_admin(email, password, name)
        click.echo(f"Administrador {email} creado.")
