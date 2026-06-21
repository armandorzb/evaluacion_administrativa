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


def build_protected_app():
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "MENTI_SEED_DEMO": True,
            "MENTI_ADMIN_PIN": "2468",
        }
    )


def build_password_app():
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "MENTI_SEED_DEMO": True,
            "MENTI_ADMIN_USERNAME": "presentador",
            "MENTI_ADMIN_PASSWORD": "secreto",
        }
    )


def build_limited_app():
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "MENTI_SEED_DEMO": True,
            "MENTI_RESPONSE_RATE_LIMIT": 1,
            "MENTI_RESPONSE_RATE_WINDOW": 60,
            "MAX_CONTENT_LENGTH": 512,
        }
    )


def test_demo_session_and_public_pages_exist():
    app = build_app()
    client = app.test_client()

    assert client.get("/admin").status_code == 200
    assert client.get("/join").status_code == 200

    payload = client.get("/api/sessions/123456").get_json()["session"]
    assert payload["code"] == "123456"
    assert len(payload["questions"]) == 4
    assert payload["questions"][0]["type"] == "content_slide"
    assert {question["type"] for question in payload["questions"]} == {"content_slide", "multiple_choice", "word_cloud", "quiz"}


def test_optional_admin_pin_protects_presenter_surfaces_but_not_audience():
    app = build_protected_app()
    client = app.test_client()

    assert client.get("/admin").status_code == 302
    assert client.get("/api/sessions").status_code == 401
    socket_client = socketio.test_client(app, flask_test_client=client)
    control = socket_client.emit("presenter_control", {"code": "123456", "action": "start"}, callback=True)
    assert control == {"ok": False, "error": "No autorizado."}
    socket_client.disconnect()
    assert client.get("/join").status_code == 200
    assert client.get("/s/123456").status_code == 200
    assert client.get("/api/sessions/123456").status_code == 200

    bad_login = client.post("/admin-login", data={"pin": "0000"})
    assert bad_login.status_code == 401

    good_login = client.post("/admin-login?next=/admin", data={"pin": "2468"})
    assert good_login.status_code == 302
    assert good_login.headers["Location"].endswith("/admin")
    assert client.get("/admin").status_code == 200
    assert client.get("/api/sessions").status_code == 200


def test_admin_username_password_can_protect_presenter_surfaces():
    app = build_password_app()
    client = app.test_client()

    assert client.get("/admin").status_code == 302
    login_page = client.get("/admin-login")
    assert login_page.status_code == 200
    assert b'name="username"' in login_page.data
    assert b'name="password"' in login_page.data

    bad_login = client.post("/admin-login", data={"username": "presentador", "password": "mal"})
    assert bad_login.status_code == 401

    good_login = client.post(
        "/admin-login?next=/admin",
        data={"username": "presentador", "password": "secreto"},
    )
    assert good_login.status_code == 302
    assert good_login.headers["Location"].endswith("/admin")
    assert client.get("/admin").status_code == 200
    assert client.get("/api/sessions").status_code == 200


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
    renamed = client.patch(f"/api/sessions/{session['code']}", json={"title": "Presentacion editada", "theme": "ocean"}).get_json()["session"]
    assert renamed["title"] == "Presentacion editada"
    assert renamed["theme"] == "ocean"

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
        {
            "type": "content_slide",
            "title": "Portada",
            "prompt": "",
            "config": {"layout": "qr", "body": "Escanea el codigo.", "show_qr": True},
        },
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


def test_content_slide_is_saved_but_does_not_accept_responses():
    app = build_app()
    client = app.test_client()
    session = client.post("/api/sessions", json={"title": "Presentacion con contenido"}).get_json()["session"]
    slide = client.post(
        f"/api/sessions/{session['code']}/questions",
        json={
            "type": "content_slide",
            "title": "Bienvenida",
            "prompt": "",
            "config": {"layout": "instructions", "body": "Lee las instrucciones.", "show_qr": False},
        },
    ).get_json()["question"]
    assert slide["config"]["layout"] == "instructions"
    assert slide["config"]["body"] == "Lee las instrucciones."

    client.post(f"/api/sessions/{session['code']}/control", json={"action": "start"})
    response = client.post(f"/api/sessions/{session['code']}/questions/{slide['id']}/responses", json={"text": "hola"})
    assert response.status_code == 400
    assert "no acepta respuestas" in response.get_json()["error"]


def test_single_choice_vote_is_replaced_for_same_participant():
    app = build_app()
    client = app.test_client()
    session = client.get("/api/sessions/123456").get_json()["session"]
    question = next(question for question in session["questions"] if question["type"] == "multiple_choice")
    question_index = [item["id"] for item in session["questions"]].index(question["id"])
    first_option, second_option = question["options"][:2]

    assert client.post("/api/sessions/123456/control", json={"action": "start"}).status_code == 200
    assert client.post("/api/sessions/123456/control", json={"action": "go_to_slide", "index": question_index}).status_code == 200
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


def test_public_response_rate_limit_and_payload_size_are_enforced():
    app = build_limited_app()
    client = app.test_client()
    session = client.post("/api/sessions", json={"title": "Sesion limitada"}).get_json()["session"]
    question = client.post(
        f"/api/sessions/{session['code']}/questions",
        json={
            "type": "multiple_choice",
            "title": "Voto",
            "prompt": "Elige",
            "options": ["A", "B"],
        },
    ).get_json()["question"]
    option_id = question["options"][0]["id"]
    client.post(f"/api/sessions/{session['code']}/control", json={"action": "start"})

    first = client.post(f"/api/sessions/{session['code']}/questions/{question['id']}/responses", json={"option_id": option_id})
    assert first.status_code == 200

    second = client.post(f"/api/sessions/{session['code']}/questions/{question['id']}/responses", json={"option_id": option_id})
    assert second.status_code == 429
    assert second.headers["Retry-After"]

    oversized = client.post(
        f"/api/sessions/{session['code']}/questions/{question['id']}/responses",
        data="x" * 800,
        content_type="application/json",
    )
    assert oversized.status_code == 413

    socket_client = socketio.test_client(app, flask_test_client=client)
    socket_response = socket_client.emit(
        "submit_response",
        {"code": session["code"], "question_id": question["id"], "payload": {"text": "x" * 800}},
        callback=True,
    )
    assert socket_response == {"ok": False, "error": "Payload demasiado grande."}
    socket_client.disconnect()


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
    quiz = next(question for question in session["questions"] if question["type"] == "quiz")
    quiz_index = [question["id"] for question in session["questions"]].index(quiz["id"])
    client.post("/api/sessions/123456/control", json={"action": "start"})
    client.post("/api/sessions/123456/control", json={"action": "go_to_slide", "index": quiz_index})

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
    word_question = next(question for question in session["questions"] if question["type"] == "word_cloud")
    word_index = [question["id"] for question in session["questions"]].index(word_question["id"])

    socket_client = socketio.test_client(app)
    join_ack = socket_client.emit("join_session", {"code": "123456"}, callback=True)
    assert join_ack["ok"] is True

    next_ack = socket_client.emit("presenter_control", {"code": "123456", "action": "go_to_slide", "index": word_index}, callback=True)
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
