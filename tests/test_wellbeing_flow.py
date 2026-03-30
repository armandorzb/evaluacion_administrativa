import zipfile
from io import BytesIO

from openpyxl import load_workbook

from municipal_diagnostico import create_app
from municipal_diagnostico.extensions import db
from municipal_diagnostico.models import BienestarEncuesta, BienestarPregunta, Usuario


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
        admin = Usuario(
            nombre="Admin",
            correo="admin@local.test",
            rol="administrador",
            activo=True,
            acceso_diagnostico=True,
            acceso_bienestar=True,
        )
        admin.set_password("secret123")
        consulta = Usuario(
            nombre="Consulta",
            correo="consulta@local.test",
            rol="consulta",
            activo=True,
            acceso_diagnostico=True,
            acceso_bienestar=True,
        )
        consulta.set_password("secret123")
        db.session.add_all([admin, consulta])
        db.session.commit()
    return app


def test_public_wellbeing_survey_can_complete_and_admin_can_open_dashboard():
    app = build_app()
    client = app.test_client()

    landing = client.get("/bienestar/")
    assert landing.status_code == 200
    assert "Bienestar Policial" in landing.get_data(as_text=True)
    public_link = client.get("/bienestar/publico")
    public_html = public_link.get_data(as_text=True)
    assert public_link.status_code == 200
    assert "Selecciona tu estrato y comienza la encuesta" in public_html
    assert "URL lista para compartir" not in public_html
    assert "Abrir panel interno" not in public_html

    questions_payload = client.get("/bienestar/api/preguntas").get_json()
    questions = questions_payload["preguntas"]
    assert len(questions) >= 35
    assert all(question["txt"].startswith("¿") and question["txt"].endswith("?") for question in questions)
    assert questions[0]["dim"] == "Bienestar Psicológico"

    start_payload = client.post("/bienestar/api/encuesta/iniciar", json={"estrato": "E3"}).get_json()
    folio = start_payload["hash"]
    assert folio

    save_payload = client.post(
        "/bienestar/api/encuesta/guardar",
        json={
            "hash": folio,
            "estado": "completada",
            "ultima_pregunta": len(questions),
            "respuestas": [{"id": question["id"], "dim": question["dim"], "val": 4} for question in questions],
        },
    ).get_json()
    assert save_payload["ok"] is True
    assert save_payload["estado"] == "completada"
    assert save_payload["iibp"] == 100.0
    assert save_payload["ivsp"] == 5.0

    survey_payload = client.get(f"/bienestar/api/encuesta/{folio}").get_json()
    assert survey_payload["estado"] == "completada"
    assert len(survey_payload["respuestas"]) == len(questions)

    survey_page = client.get(f"/bienestar/encuesta?folio={folio}")
    survey_html = survey_page.get_data(as_text=True)
    assert survey_page.status_code == 200
    assert "Menú" not in survey_html
    assert "Acceso interno" not in survey_html

    login(client, "admin@local.test")
    dashboard = client.get("/bienestar/panel")
    html = dashboard.get_data(as_text=True)
    assert dashboard.status_code == 200
    assert "Panel interno de Bienestar Policial" in html
    assert "IIBP promedio" in html
    assert "/bienestar/publico" in html

    pdf_export = client.get("/bienestar/exportar/pdf")
    assert pdf_export.status_code == 200
    assert pdf_export.mimetype == "application/pdf"
    assert pdf_export.data.startswith(b"%PDF")

    xlsx_export = client.get("/bienestar/exportar/xlsx")
    assert xlsx_export.status_code == 200
    assert xlsx_export.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    workbook = load_workbook(BytesIO(xlsx_export.data))
    assert "Resumen" in workbook.sheetnames
    summary_values = [
        value
        for row in workbook["Resumen"].iter_rows(values_only=True)
        for value in row
        if isinstance(value, str)
    ]
    assert any("Reporte ejecutivo de bienestar institucional" in value for value in summary_values)

    word_export = client.get("/bienestar/exportar/word")
    assert word_export.status_code == 200
    assert word_export.mimetype == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    with zipfile.ZipFile(BytesIO(word_export.data)) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
    assert "Reporte ejecutivo de bienestar institucional" in document_xml

    csv_export = client.get("/bienestar/exportar/csv")
    assert csv_export.status_code == 200
    assert csv_export.mimetype == "text/csv"
    assert "pregunta_1" in csv_export.get_data(as_text=True)

    with app.app_context():
        survey_record = BienestarEncuesta.query.filter_by(hash_id=folio).first()
        assert survey_record is not None
        assert survey_record.estado == "completada"


def test_admin_can_manage_wellbeing_questions_and_consulta_is_read_only():
    app = build_app()
    client = app.test_client()

    login(client, "admin@local.test")
    response = client.post(
        "/bienestar/preguntas",
        data={
            "action": "add",
            "orden": 99,
            "dimension": "Clima Laboral",
            "texto": "Existe un ambiente colaborativo en su unidad?",
            "opcion_1": "Siempre",
            "opcion_2": "Casi siempre",
            "opcion_3": "A veces",
            "opcion_4": "Nunca",
        },
        follow_redirects=True,
    )
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Pregunta creada." in html
    assert "Clima Laboral" in html

    with app.app_context():
        question = BienestarPregunta.query.filter_by(orden=99).first()
        assert question is not None
        assert question.texto == "¿Existe un ambiente colaborativo en su unidad?"
        question_id = question.id

    toggle = client.post(
        "/bienestar/preguntas",
        data={"action": "toggle", "question_id": question_id},
        follow_redirects=True,
    )
    assert toggle.status_code == 200
    assert "Pregunta desactivada." in toggle.get_data(as_text=True)

    client.get("/auth/logout", follow_redirects=True)
    login(client, "consulta@local.test")
    assert client.get("/bienestar/preguntas").status_code == 403
    dashboard = client.get("/bienestar/panel")
    assert dashboard.status_code == 200
    assert "Panel interno de Bienestar Policial" in dashboard.get_data(as_text=True)
    assert client.get("/bienestar/exportar/pdf").status_code == 200
    assert client.get("/bienestar/exportar/xlsx").status_code == 200
    assert client.get("/bienestar/exportar/word").status_code == 200


def test_partial_progress_can_be_recovered_by_folio():
    app = build_app()
    client = app.test_client()

    questions = client.get("/bienestar/api/preguntas").get_json()["preguntas"]
    folio = client.post("/bienestar/api/encuesta/iniciar", json={"estrato": "E2"}).get_json()["hash"]

    save_response = client.post(
        "/bienestar/api/encuesta/guardar",
        json={
            "hash": folio,
            "estado": "en_progreso",
            "ultima_pregunta": 3,
            "respuestas": [{"id": question["id"], "dim": question["dim"], "val": 3} for question in questions[:3]],
        },
    )
    assert save_response.status_code == 200
    payload = save_response.get_json()
    assert payload["estado"] == "en_progreso"

    recovery = client.get(f"/bienestar/api/encuesta/{folio}").get_json()
    assert recovery["estado"] == "en_progreso"
    assert recovery["ultima_pregunta"] == 3
    assert len(recovery["respuestas"]) == 3
