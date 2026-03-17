from datetime import date

from municipal_diagnostico import create_app
from municipal_diagnostico.extensions import db
from municipal_diagnostico.models import (
    Area,
    AsignacionCuestionario,
    CampanaCuestionario,
    CuestionarioVersion,
    Dependencia,
    EjeVersion,
    ReactivoVersion,
    RespuestaAsignacion,
    SoporteSeccion,
    Usuario,
)


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


def create_simple_questionnaire() -> CuestionarioVersion:
    version = CuestionarioVersion(
        nombre="Cuestionario simplificado",
        descripcion="Instrumento reducido para pruebas",
        estado="publicado",
    )
    db.session.add(version)
    db.session.flush()

    options = {
        "0": "No existe",
        "1": "Inicial",
        "2": "En proceso",
        "3": "Consolidado",
    }
    axis_specs = [
        ("E1", "Planeacion", 1, 0.5),
        ("E2", "Control", 2, 0.5),
    ]
    for axis_key, axis_name, order, weight in axis_specs:
        axis = EjeVersion(
            cuestionario_version=version,
            clave=axis_key,
            nombre=axis_name,
            orden=order,
            ponderacion=weight,
        )
        db.session.add(axis)
        db.session.flush()
        for reactive_order in range(1, 3):
            db.session.add(
                ReactivoVersion(
                    eje_version=axis,
                    codigo=f"{axis_key}-{reactive_order}",
                    orden=reactive_order,
                    pregunta=f"Pregunta {reactive_order} de {axis_name}",
                    opciones=options,
                )
            )
    return version


def build_app_with_campaign_data():
    app = create_app(TestConfig)
    with app.app_context():
        dependency_one = Dependencia(nombre="Oficialia", tipo="Administrativa")
        dependency_two = Dependencia(nombre="Tesoreria", tipo="Administrativa")
        area_one = Area(nombre="RH", dependencia=dependency_one)
        area_two = Area(nombre="Ingresos", dependencia=dependency_two)

        admin = Usuario(nombre="Admin", correo="admin@local.test", rol="administrador", activo=True)
        admin.set_password("secret123")
        respondent = Usuario(
            nombre="Respondente",
            correo="respondente@local.test",
            rol="respondente",
            activo=True,
            dependencia=dependency_one,
            area=area_one,
        )
        respondent.set_password("secret123")
        consulta = Usuario(
            nombre="Consulta",
            correo="consulta@local.test",
            rol="consulta",
            activo=True,
        )
        consulta.set_password("secret123")

        questionnaire = create_simple_questionnaire()
        campaign = CampanaCuestionario(
            nombre="Campana 2026",
            descripcion="Campana de seguimiento",
            estado="activa",
            fecha_apertura=date(2026, 1, 1),
            fecha_limite=date(2026, 12, 31),
            cuestionario_version=questionnaire,
            creado_por=admin,
        )

        db.session.add_all([dependency_one, dependency_two, area_one, area_two, admin, respondent, consulta, campaign])
        db.session.commit()

        return app, {
            "campaign_id": campaign.id,
            "questionnaire_id": questionnaire.id,
            "dependency_two_id": dependency_two.id,
            "respondent_id": respondent.id,
            "axis_one_id": questionnaire.ejes[0].id,
            "axis_two_id": questionnaire.ejes[1].id,
            "axis_one_reactives": [reactive.id for reactive in questionnaire.ejes[0].reactivos],
            "axis_two_reactives": [reactive.id for reactive in questionnaire.ejes[1].reactivos],
        }


def complete_axis(assignment, axis, user, value: int, comment: str):
    for reactive in axis.reactivos:
        db.session.add(
            RespuestaAsignacion(
                asignacion=assignment,
                reactivo_version=reactive,
                usuario=user,
                valor=value,
                comentario=comment,
            )
        )
    db.session.add(
        SoporteSeccion(
            asignacion=assignment,
            eje_version=axis,
            usuario=user,
            comentario=f"Soporte {axis.nombre}",
        )
    )


def test_admin_can_create_mixed_assignments_and_open_simplified_reports():
    app, ids = build_app_with_campaign_data()
    client = app.test_client()

    login(client, "admin@local.test")
    response = client.post(
        "/campanas/asignaciones",
        data={
            "action": "add_assignments",
            "campana_id": ids["campaign_id"],
            "usuario_ids": [str(ids["respondent_id"])],
            "dependencia_ids": [str(ids["dependency_two_id"])],
            "respondente_id": str(ids["respondent_id"]),
        },
        follow_redirects=True,
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Asignaciones registradas: 2." in html
    assert "Distribucion operativa del cuestionario" in html

    with app.app_context():
        assignments = AsignacionCuestionario.query.filter_by(campana_id=ids["campaign_id"]).all()
        assert len(assignments) == 2
        assert {assignment.target_type for assignment in assignments} == {"usuario", "dependencia"}

    report = client.get(f"/campanas/reportes?campana_id={ids['campaign_id']}")
    report_html = report.get_data(as_text=True)

    assert report.status_code == 200
    assert "Seguimiento por campana, asignado y seccion" in report_html
    assert "Respondente" in report_html
    assert "Tesoreria" in report_html


def test_respondente_can_autosave_complete_and_submit_assignment():
    app, ids = build_app_with_campaign_data()
    with app.app_context():
        respondent = Usuario.query.filter_by(correo="respondente@local.test").first()
        campaign = CampanaCuestionario.query.get(ids["campaign_id"])
        assignment = AsignacionCuestionario(
            campana=campaign,
            target_type="usuario",
            usuario=respondent,
            dependencia=respondent.dependencia,
            respondente=respondent,
            estado="pendiente",
        )
        db.session.add(assignment)
        db.session.commit()
        assignment_id = assignment.id

    client = app.test_client()
    login(client, "respondente@local.test")

    autosave = client.post(
        f"/campanas/asignaciones/{assignment_id}/autosave",
        json={
            "eje_id": ids["axis_one_id"],
            "comentario_eje": "Seccion inicial contestada",
            "responses": [
                {"reactivo_id": ids["axis_one_reactives"][0], "valor": 3, "comentario": "Avance alto"},
                {"reactivo_id": ids["axis_one_reactives"][1], "valor": 2, "comentario": "Avance medio"},
            ],
        },
    )
    payload = autosave.get_json()

    assert autosave.status_code == 200
    assert payload["ok"] is True
    assert payload["completion"] == 50.0

    save_axis_two = client.post(
        f"/campanas/asignaciones/{assignment_id}",
        data={
            "eje_id": ids["axis_two_id"],
            f"valor_{ids['axis_two_reactives'][0]}": "3",
            f"comentario_{ids['axis_two_reactives'][0]}": "Completo",
            f"valor_{ids['axis_two_reactives'][1]}": "3",
            f"comentario_{ids['axis_two_reactives'][1]}": "Completo",
            f"comentario_eje_{ids['axis_two_id']}": "Segunda seccion contestada",
        },
        follow_redirects=True,
    )
    assert save_axis_two.status_code == 200
    assert "Seccion guardada." in save_axis_two.get_data(as_text=True)

    submit = client.post(f"/campanas/asignaciones/{assignment_id}/enviar", follow_redirects=True)
    submit_html = submit.get_data(as_text=True)

    assert submit.status_code == 200
    assert "Cuestionario enviado." in submit_html

    report = client.get(f"/campanas/reportes/asignaciones/{assignment_id}")
    assert report.status_code == 200
    assert "Reporte detallado" in report.get_data(as_text=True)

    with app.app_context():
        saved_assignment = db.session.get(AsignacionCuestionario, assignment_id)
        assert saved_assignment.estado == "respondido"
        assert saved_assignment.progreso == 100


def test_consulta_only_sees_final_assignments_in_simplified_reports():
    app, ids = build_app_with_campaign_data()
    with app.app_context():
        respondent = Usuario.query.filter_by(correo="respondente@local.test").first()
        campaign = db.session.get(CampanaCuestionario, ids["campaign_id"])
        ready_assignment = AsignacionCuestionario(
            campana=campaign,
            target_type="usuario",
            usuario=respondent,
            dependencia=respondent.dependencia,
            respondente=respondent,
            estado="respondido",
            progreso=100,
        )
        pending_assignment = AsignacionCuestionario(
            campana=campaign,
            target_type="dependencia",
            dependencia=Dependencia.query.filter_by(nombre="Tesoreria").first(),
            respondente=respondent,
            estado="pendiente",
            progreso=0,
        )
        db.session.add_all([ready_assignment, pending_assignment])
        db.session.flush()
        complete_axis(ready_assignment, campaign.cuestionario_version.ejes[0], respondent, 3, "Completo")
        complete_axis(ready_assignment, campaign.cuestionario_version.ejes[1], respondent, 2, "Completo")
        db.session.commit()

    client = app.test_client()
    login(client, "consulta@local.test")

    response = client.get(f"/campanas/reportes?campana_id={ids['campaign_id']}")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Respondente" in html
    assert "Tesoreria" not in html
    assert client.get("/campanas/asignaciones").status_code == 403
