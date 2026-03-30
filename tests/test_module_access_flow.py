from municipal_diagnostico import create_app
from municipal_diagnostico.extensions import db
from municipal_diagnostico.models import Usuario


class TestConfig:
    SECRET_KEY = "test"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = "tests/uploads"
    ALLOWED_EXTENSIONS = {"pdf"}
    AUTO_INIT_DATABASE = True
    BOOTSTRAP_ADMIN_EMAIL = None
    BOOTSTRAP_ADMIN_PASSWORD = None
    BOOTSTRAP_ADMIN_NAME = None


def login(client, email: str, password: str = "secret123"):
    return client.post(
        "/auth/login",
        data={"correo": email, "password": password},
        follow_redirects=True,
    )


def build_app():
    app = create_app(TestConfig)
    with app.app_context():
        users = [
            Usuario(
                nombre="Dual Admin",
                correo="dual@test.local",
                rol="administrador",
                activo=True,
                acceso_diagnostico=True,
                acceso_bienestar=True,
            ),
            Usuario(
                nombre="Solo Diagnostico",
                correo="diagnostico@test.local",
                rol="administrador",
                activo=True,
                acceso_diagnostico=True,
                acceso_bienestar=False,
            ),
            Usuario(
                nombre="Solo Bienestar",
                correo="bienestar@test.local",
                rol="consulta",
                activo=True,
                acceso_diagnostico=False,
                acceso_bienestar=True,
            ),
            Usuario(
                nombre="Sin Modulos",
                correo="sinmodulos@test.local",
                rol="consulta",
                activo=True,
                acceso_diagnostico=False,
                acceso_bienestar=False,
            ),
        ]
        for user in users:
            user.set_password("secret123")
        db.session.add_all(users)
        db.session.commit()
    return app


def test_login_routes_users_to_the_correct_module_shell():
    app = build_app()
    client = app.test_client()

    dual_response = login(client, "dual@test.local")
    dual_html = dual_response.get_data(as_text=True)
    assert dual_response.status_code == 200
    assert "Selecciona el módulo" in dual_html
    assert "Diagnóstico Integral Municipal" in dual_html
    assert "Bienestar Policial" in dual_html

    client.get("/auth/logout", follow_redirects=True)

    diagnostic_response = login(client, "diagnostico@test.local")
    diagnostic_html = diagnostic_response.get_data(as_text=True)
    assert diagnostic_response.status_code == 200
    assert "Tablero administrativo" in diagnostic_html
    assert "Bienestar Policial" not in diagnostic_html

    client.get("/auth/logout", follow_redirects=True)

    wellbeing_response = login(client, "bienestar@test.local")
    wellbeing_html = wellbeing_response.get_data(as_text=True)
    assert wellbeing_response.status_code == 200
    assert "Panel interno de Bienestar Policial" in wellbeing_html
    assert "Cuestionarios" not in wellbeing_html


def test_user_without_modules_cannot_log_in_operatively():
    app = build_app()
    client = app.test_client()

    response = login(client, "sinmodulos@test.local")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "módulos asignados" in html
    assert "Iniciar sesi" in html


def test_module_guards_block_cross_module_access():
    app = build_app()
    client = app.test_client()

    login(client, "diagnostico@test.local")
    wellbeing_denied = client.get("/bienestar/panel")
    assert wellbeing_denied.status_code == 403
    assert "Bienestar Policial" in wellbeing_denied.get_data(as_text=True)

    client.get("/auth/logout", follow_redirects=True)
    login(client, "bienestar@test.local")
    diagnostic_denied = client.get("/admin/catalogos")
    assert diagnostic_denied.status_code == 403
    assert "Diagnóstico Integral Municipal" in diagnostic_denied.get_data(as_text=True)


def test_admin_catalogs_validate_module_assignment_rules():
    app = build_app()
    client = app.test_client()

    login(client, "dual@test.local")

    invalid_role = client.post(
        "/admin/catalogos",
        data={
            "action": "add_usuario",
            "redirect_anchor": "catalogo-usuarios",
            "nombre": "Revisor Bienestar",
            "correo": "revisorbienestar@test.local",
            "password": "secret123",
            "rol": "revisor",
            "acceso_diagnostico": "on",
            "acceso_bienestar": "on",
        },
        follow_redirects=True,
    )
    assert invalid_role.status_code == 200
    with app.app_context():
        assert Usuario.query.filter_by(correo="revisorbienestar@test.local").first() is None

    invalid_without_modules = client.post(
        "/admin/catalogos",
        data={
            "action": "add_usuario",
            "redirect_anchor": "catalogo-usuarios",
            "nombre": "Sin Modulos",
            "correo": "nuevosinmodulos@test.local",
            "password": "secret123",
            "rol": "consulta",
        },
        follow_redirects=True,
    )
    assert invalid_without_modules.status_code == 200
    with app.app_context():
        assert Usuario.query.filter_by(correo="nuevosinmodulos@test.local").first() is None

    valid_default_consulta = client.post(
        "/admin/catalogos",
        data={
            "action": "add_usuario",
            "redirect_anchor": "catalogo-usuarios",
            "nombre": "Consulta Diagnostico",
            "correo": "consultadiagnostico@test.local",
            "password": "secret123",
            "rol": "consulta",
            "acceso_diagnostico": "on",
        },
        follow_redirects=True,
    )
    assert valid_default_consulta.status_code == 200

    with app.app_context():
        created_default_user = Usuario.query.filter_by(correo="consultadiagnostico@test.local").first()
        assert created_default_user is not None
        assert created_default_user.acceso_diagnostico is True
        assert created_default_user.acceso_bienestar is False

    valid_wellbeing_only = client.post(
        "/admin/catalogos",
        data={
            "action": "add_usuario",
            "redirect_anchor": "catalogo-usuarios",
            "nombre": "Consulta Bienestar",
            "correo": "consultabienestar@test.local",
            "password": "secret123",
            "rol": "consulta",
            "acceso_bienestar": "on",
        },
        follow_redirects=True,
    )
    assert valid_wellbeing_only.status_code == 200

    with app.app_context():
        created_user = Usuario.query.filter_by(correo="consultabienestar@test.local").first()
        assert created_user is not None
        assert created_user.acceso_diagnostico is False
        assert created_user.acceso_bienestar is True

    client.get("/auth/logout", follow_redirects=True)
    redirected = login(client, "consultabienestar@test.local")
    assert redirected.status_code == 200
    assert "Panel interno de Bienestar Policial" in redirected.get_data(as_text=True)
