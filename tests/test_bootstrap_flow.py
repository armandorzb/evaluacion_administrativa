from municipal_diagnostico import create_app


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


def test_login_and_bootstrap_routes_work_on_fresh_database():
    app = create_app(TestConfig)
    client = app.test_client()

    assert client.get("/auth/login").status_code == 200
    assert client.get("/auth/bootstrap").status_code == 200
