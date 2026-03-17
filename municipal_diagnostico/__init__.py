import logging
import os

from flask import Flask, redirect, url_for
from flask_login import current_user
from sqlalchemy import inspect, text

from config import Config
from municipal_diagnostico.blueprints.admin import bp as admin_bp
from municipal_diagnostico.blueprints.auth import bp as auth_bp
from municipal_diagnostico.blueprints.campaigns import bp as campaigns_bp
from municipal_diagnostico.blueprints.dashboard import bp as dashboard_bp
from municipal_diagnostico.blueprints.evaluation import bp as evaluation_bp
from municipal_diagnostico.blueprints.reports import bp as reports_bp
from municipal_diagnostico.extensions import db, login_manager, migrate
from municipal_diagnostico.models import Notificacion, Usuario
from municipal_diagnostico.seeds import bootstrap_admin, ensure_official_questionnaire, register_cli_commands
from municipal_diagnostico.timeutils import app_timezone, to_localtime, utcnow


def create_app(config_object: type[Config] = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    configure_logging(app)
    init_extensions(app)
    register_blueprints(app)
    register_context_processors(app)
    register_error_handlers(app)
    register_cli_commands(app)
    ensure_database_ready(app)

    return app


def configure_logging(app: Flask) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    app.logger.setLevel(logging.INFO)


def init_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id: str) -> Usuario | None:
        return db.session.get(Usuario, int(user_id))


def ensure_database_ready(app: Flask) -> None:
    with app.app_context():
        inspector = inspect(db.engine)
        auto_init = app.config.get("AUTO_INIT_DATABASE", False)
        uri = app.config["SQLALCHEMY_DATABASE_URI"]
        has_user_table = inspector.has_table("usuario")

        if not auto_init and not uri.startswith("sqlite") and has_user_table:
            return
        if not auto_init and not uri.startswith("sqlite") and not has_user_table:
            app.logger.warning(
                "La base de datos no está inicializada y AUTO_INIT_DATABASE está desactivado."
            )
            return

        db.create_all()
        ensure_schema_compatibility(app)
        ensure_official_questionnaire()

        if not has_user_table:
            email = app.config.get("BOOTSTRAP_ADMIN_EMAIL")
            password = app.config.get("BOOTSTRAP_ADMIN_PASSWORD")
            if email:
                bootstrap_admin(
                    email=email,
                    password=password,
                    name=app.config.get("BOOTSTRAP_ADMIN_NAME"),
                )

            app.logger.info("Base de datos inicializada automáticamente.")


def ensure_schema_compatibility(app: Flask) -> None:
    inspector = inspect(db.engine)
    if inspector.has_table("area"):
        columns = {column["name"] for column in inspector.get_columns("area")}
        if "activa" not in columns:
            with db.engine.begin() as connection:
                connection.execute(text("ALTER TABLE area ADD COLUMN activa BOOLEAN NOT NULL DEFAULT 1"))
            app.logger.info("Columna area.activa agregada automáticamente.")


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(campaigns_bp)
    app.register_blueprint(evaluation_bp)
    app.register_blueprint(reports_bp)

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard.home"))
        return redirect(url_for("auth.login"))


def register_context_processors(app: Flask) -> None:
    @app.context_processor
    def inject_layout_context():
        if not current_user.is_authenticated:
            return {"unread_notifications": 0, "recent_notifications": [], "app_timezone": str(app_timezone())}

        notifications = (
            Notificacion.query.filter_by(usuario_id=current_user.id)
            .order_by(Notificacion.created_at.desc())
            .limit(5)
            .all()
        )
        unread = sum(1 for notification in notifications if not notification.leida)
        return {
            "current_year": utcnow().year,
            "unread_notifications": unread,
            "recent_notifications": notifications,
            "app_timezone": str(app_timezone()),
        }

    @app.template_filter("datetimeformat")
    def datetimeformat(value, pattern: str = "%d/%m/%Y %H:%M"):
        if not value:
            return "-"
        local_value = to_localtime(value)
        return local_value.strftime(pattern) if local_value else "-"

    @app.template_filter("percent")
    def percent(value):
        return f"{value * 100:.0f}%"


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(403)
    def forbidden(_error):
        return (
            "No cuentas con permisos para acceder a este recurso.",
            403,
        )
