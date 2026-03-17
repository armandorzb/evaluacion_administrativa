from datetime import date

from municipal_diagnostico import create_app
from municipal_diagnostico.extensions import db
from municipal_diagnostico.models import Dependencia, Evaluacion, PeriodoEvaluacion, Respuesta, Usuario
from municipal_diagnostico.seeds import ensure_official_questionnaire
from municipal_diagnostico.services.analytics import summarize_evaluation


class TestConfig:
    SECRET_KEY = "test"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = "tests/uploads"
    ALLOWED_EXTENSIONS = {"pdf"}
    BOOTSTRAP_ADMIN_EMAIL = None
    BOOTSTRAP_ADMIN_PASSWORD = None
    BOOTSTRAP_ADMIN_NAME = None


def test_weighted_index_uses_zero_for_missing_answers():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        questionnaire = ensure_official_questionnaire()
        dependency = Dependencia(nombre="Dependencia Test", tipo="Administrativa")
        user = Usuario(nombre="Capturista", correo="captura@test.local", rol="evaluador", activo=True, dependencia=dependency)
        user.set_password("secret123")
        period = PeriodoEvaluacion(
            nombre="Periodo Test",
            estado="abierto",
            fecha_inicio=date(2026, 1, 1),
            fecha_cierre=date(2026, 12, 31),
            cuestionario_version=questionnaire,
        )
        evaluation = Evaluacion(periodo=period, dependencia=dependency, estado="en_captura")
        db.session.add_all([dependency, user, period, evaluation])
        db.session.flush()

        first_axis = questionnaire.ejes[0]
        for reactivo in first_axis.reactivos[:5]:
            db.session.add(
                Respuesta(
                    evaluacion=evaluation,
                    reactivo_version=reactivo,
                    usuario_captura=user,
                    valor=3,
                )
            )
        db.session.commit()

        summary = summarize_evaluation(evaluation)

        assert summary["answered_questions"] == 5
        assert summary["total_questions"] == 80
        assert summary["axes"][0]["promedio"] == 1.5
