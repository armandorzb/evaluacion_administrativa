from datetime import timedelta

from mentimeter_live_app.app import create_app, socketio
from mentimeter_live_app.models import db, Question, Response, Session, utcnow


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MENTI_SEED_DEMO = True


def build_app():
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "MENTI_SEED_DEMO": True,
        }
    )


def test_demo_session_and_public_pages_exist():
    app = build_app()
    client = app.test_client()

    assert client.get("/admin").status_code == 200
    assert client.get("/join").status_code == 200

    payload = client.get("/api/sessions/123456").get_json()["session"]
    assert payload["code"] == "123456"
    assert len(payload["questions"]) == 3
    assert {question["type"] for question in payload["questions"]} == {"multiple_choice", "word_cloud", "quiz"}


def test_presenter_can_create_edit_delete_and_reorder_questions():
    app = build_app()
    client = app.test_client()

    created = client.post("/api/sessions", json={"title": "Taller ciudadano"})
    assert created.status_code == 201
    session = created.get_json()["session"]
    assert len(session["code"]) == 6

    first = client.post(
        f"/api/sessions/{session['code']}/questions",
        json={
            "type": "multiple_choice",
            "title": "Prioridad",
            "prompt": "Elige una",
            "options": ["A", "B"],
        },
    ).get_json()["question"]
    second = client.post(
        f"/api/sessions/{session['code']}/questions",
        json={
            "type": "scale",
            "title": "Calificacion",
            "prompt": "Califica",
            "config": {"min": 1, "max": 5},
        },
    ).get_json()["question"]

    edited = client.patch(
        f"/api/sessions/{session['code']}/questions/{first['id']}",
        json={"title": "Prioridad actualizada"},
    ).get_json()["question"]
    assert edited["title"] == "Prioridad actualizada"

    reordered = client.post(
        f"/api/sessions/{session['code']}/questions/reorder",
        json={"question_ids": [second["id"], first["id"]]},
    ).get_json()["session"]
    assert [question["id"] for question in reordered["questions"]] == [second["id"], first["id"]]

    deleted = client.delete(f"/api/sessions/{session['code']}/questions/{first['id']}").get_json()["session"]
    assert [question["id"] for question in deleted["questions"]] == [second["id"]]


def test_templates_duplicate_theme_exports_and_insights_are_available():
    app = build_app()
    client = app.test_client()

    templates = client.get("/api/question-templates").get_json()["templates"]
    assert templates

    session = client.post("/api/sessions", json={"title": "Taller con plantillas"}).get_json()["session"]
    created = client.post(f"/api/sessions/{session['code']}/questions", json=templates[0]["payload"]).get_json()["question"]
    duplicated = client.post(f"/api/sessions/{session['code']}/questions/{created['id']}/duplicate").get_json()["session"]
    assert len(duplicated["questions"]) == 2

    themed = client.post(f"/api/sessions/{session['code']}/control", json={"action": "set_theme", "theme": "contrast"}).get_json()["session"]
    assert themed["theme"] == "contrast"

    insights = client.get(f"/api/sessions/{session['code']}/insights").get_json()["insights"]
    assert insights["question_count"] == 2
    assert client.get(f"/api/sessions/{session['code']}/export.csv").status_code == 200
    assert client.get(f"/api/sessions/{session['code']}/export.xlsx").status_code == 200
    assert client.get(f"/api/sessions/{session['code']}/export.pdf").status_code == 200
    assert client.get("/healthz").get_json()["ok"] is True


def test_all_required_question_types_can_be_created():
    app = build_app()
    client = app.test_client()
    session = client.post("/api/sessions", json={"title": "Tipos requeridos"}).get_json()["session"]
    code = session["code"]

    examples = [
        {"type": "multiple_choice", "title": "Opcion", "prompt": "Elige", "options": ["A", "B"]},
        {"type": "word_cloud", "title": "Nube", "prompt": "Una palabra"},
        {"type": "scale", "title": "Escala", "prompt": "Califica", "config": {"min": 1, "max": 10}},
        {"type": "open_text", "title": "Abierta", "prompt": "Opina"},
        {"type": "ranking", "title": "Ranking", "prompt": "Ordena", "options": ["A", "B", "C"]},
        {
            "type": "quiz",
            "title": "Quiz",
            "prompt": "Correcta",
            "options": ["A", "B"],
            "correct_option_labels": ["B"],
            "config": {"timer_seconds": 20, "points": 50},
        },
    ]

    created_types = []
    for payload in examples:
        response = client.post(f"/api/sessions/{code}/questions", json=payload)
        assert response.status_code == 201
        created_types.append(response.get_json()["question"]["type"])

    assert created_types == [item["type"] for item in examples]


def test_single_choice_vote_is_replaced_for_same_participant():
    app = build_app()
    client = app.test_client()
    session = client.get("/api/sessions/123456").get_json()["session"]
    question = session["questions"][0]
    first_option, second_option = question["options"][:2]

    assert client.post("/api/sessions/123456/control", json={"action": "start"}).status_code == 200
    assert client.post(
        f"/api/sessions/123456/questions/{question['id']}/responses",
        json={"option_id": first_option["id"]},
    ).status_code == 200
    payload = client.post(
        f"/api/sessions/123456/questions/{question['id']}/responses",
        json={"option_id": second_option["id"]},
    ).get_json()
    assert payload["ok"] is True

    with app.app_context():
        db_session = Session.query.filter_by(code="123456").first()
        responses = Response.query.filter_by(session_id=db_session.id, question_id=question["id"]).all()
        assert len(responses) == 1
        assert responses[0].payload_json["option_id"] == second_option["id"]

    counts = {item["id"]: item["count"] for item in payload["results"]["options"]}
    assert counts[first_option["id"]] == 0
    assert counts[second_option["id"]] == 1


def test_manual_moderation_hides_then_reveals_open_text_results():
    app = build_app()
    client = app.test_client()
    session = client.post("/api/sessions", json={"title": "Moderacion"}).get_json()["session"]
    question = client.post(
        f"/api/sessions/{session['code']}/questions",
        json={
            "type": "word_cloud",
            "title": "Ideas",
            "prompt": "Una palabra",
            "config": {"moderation": "manual"},
        },
    ).get_json()["question"]
    client.post(f"/api/sessions/{session['code']}/control", json={"action": "start"})

    submitted = client.post(
        f"/api/sessions/{session['code']}/questions/{question['id']}/responses",
        json={"text": "integridad"},
    ).get_json()
    assert submitted["results"]["words"] == []

    state = client.get(f"/api/sessions/{session['code']}").get_json()["session"]
    pending = state["questions"][0]["pending_responses"][0]
    approved = client.post(
        f"/api/sessions/{session['code']}/questions/{question['id']}/responses/{pending['id']}/moderate",
        json={"action": "approve"},
    ).get_json()
    assert approved["results"]["words"][0]["text"] == "integridad"


def test_quiz_timer_is_enforced_by_server_state():
    app = build_app()
    client = app.test_client()
    session = client.get("/api/sessions/123456").get_json()["session"]
    quiz = session["questions"][2]
    client.post("/api/sessions/123456/control", json={"action": "start"})
    client.post("/api/sessions/123456/control", json={"action": "next"})
    client.post("/api/sessions/123456/control", json={"action": "next"})

    with app.app_context():
        question = db.session.get(Question, quiz["id"])
        config = dict(question.config_json)
        config["timer_started_at"] = (utcnow() - timedelta(seconds=config["timer_seconds"] + 5)).isoformat()
        question.config_json = config
        db.session.commit()

    refreshed = client.get("/api/sessions/123456").get_json()["session"]
    refreshed_quiz = next(question for question in refreshed["questions"] if question["id"] == quiz["id"])
    assert refreshed_quiz["is_open"] is False
    assert refreshed_quiz["timer"]["remaining"] == 0


def test_socketio_join_navigation_and_live_results():
    app = build_app()
    client = app.test_client()
    session = client.post("/api/sessions/123456/control", json={"action": "start"}).get_json()["session"]
    word_question = session["questions"][1]

    socket_client = socketio.test_client(app)
    join_ack = socket_client.emit("join_session", {"code": "123456"}, callback=True)
    assert join_ack["ok"] is True

    next_ack = socket_client.emit("presenter_control", {"code": "123456", "action": "next"}, callback=True)
    assert next_ack["ok"] is True
    assert next_ack["session"]["active_question_id"] == word_question["id"]

    submit_ack = socket_client.emit(
        "submit_response",
        {
            "code": "123456",
            "question_id": word_question["id"],
            "participant_token": join_ack["participant_token"],
            "payload": {"text": "transparencia"},
        },
        callback=True,
    )
    assert submit_ack["ok"] is True
    assert submit_ack["results"]["words"][0]["text"] == "transparencia"
    received = socket_client.get_received()
    assert any(item["name"] == "results_updated" for item in received)
