from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from io import BytesIO, StringIO
import os
from pathlib import Path
from random import randint
from secrets import token_urlsafe
from typing import Any

import qrcode
from flask import Flask, abort, jsonify, make_response, redirect, render_template, request, send_file, url_for
from flask_socketio import SocketIO, emit, join_room
from werkzeug.middleware.proxy_fix import ProxyFix
from openpyxl import Workbook
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

try:
    from .models import db, Option, Participant, Question, Response, Session, utcnow
except ImportError:  # Allows `python app.py` from this folder.
    from models import db, Option, Participant, Question, Response, Session, utcnow


socketio = SocketIO(async_mode="threading", cors_allowed_origins="*", manage_session=False)
# Contract shared by backend validation and the two vanilla JS frontends.
QUESTION_TYPES = {"multiple_choice", "word_cloud", "scale", "open_text", "ranking", "quiz"}
SINGLE_RESPONSE_TYPES = {"multiple_choice", "scale", "ranking", "quiz"}
PARTICIPANT_COOKIE = "menti_participant_token"
socket_participants: dict[str, tuple[int, str]] = {}


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    database_url = os.getenv("DATABASE_URL")
    local_database = Path(os.getenv("MENTI_DB_PATH", str(Path(app.instance_path) / "mentimeter.sqlite3")))
    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY", "dev-mentimeter-local"),
        SQLALCHEMY_DATABASE_URI=database_url or f"sqlite:///{local_database}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MENTI_SEED_DEMO=os.getenv("MENTI_SEED_DEMO", "true").lower() in {"1", "true", "yes", "si"},
        MENTI_SOCKETIO_CORS=os.getenv("MENTI_SOCKETIO_CORS", "*"),
    )
    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    if not database_url:
        local_database.parent.mkdir(parents=True, exist_ok=True)
    db.init_app(app)
    if os.getenv("MENTI_PROXY_FIX", "false").lower() in {"1", "true", "yes", "si"}:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    socketio.init_app(app, cors_allowed_origins=app.config["MENTI_SOCKETIO_CORS"])
    register_routes(app)
    register_socket_events()

    with app.app_context():
        db.create_all()
        if app.config.get("MENTI_SEED_DEMO", True):
            ensure_demo_session()

    return app


def register_routes(app: Flask) -> None:
    @app.get("/")
    def index():
        return redirect(url_for("join"))

    @app.get("/healthz")
    def healthz():
        return jsonify({"ok": True, "service": "mentimeter_live_app"})

    @app.get("/admin")
    def admin():
        sessions = Session.query.order_by(Session.updated_at.desc()).all()
        selected = find_session(request.args.get("code")) if request.args.get("code") else (sessions[0] if sessions else None)
        return render_template("admin.html", sessions=sessions, selected=selected, question_types=sorted(QUESTION_TYPES))

    @app.get("/present/<code>")
    def present(code: str):
        session = find_session(code)
        if session is None:
            abort(404)
        return render_template("admin.html", sessions=[session], selected=session, question_types=sorted(QUESTION_TYPES), present_only=True)

    @app.route("/join", methods=["GET", "POST"])
    def join():
        code = request.values.get("code", "").strip()
        if request.method == "POST" or code:
            session = find_session(code)
            if session is None:
                return render_template("join.html", error="No encontramos una sesion con ese codigo.", code=code), 404
            return redirect(url_for("audience", code=session.code))
        return render_template("join.html")

    @app.get("/s/<code>")
    def audience(code: str):
        session = find_session(code)
        if session is None:
            abort(404)
        participant = get_or_create_participant(session, request.cookies.get(PARTICIPANT_COOKIE))
        db.session.commit()
        response = make_response(render_template("audience.html", session=session, participant=participant))
        response.set_cookie(PARTICIPANT_COOKIE, participant.token, httponly=True, samesite="Lax")
        return response

    @app.get("/qr/<code>.png")
    def qr_png(code: str):
        session = find_session(code)
        if session is None:
            abort(404)
        qr_url = url_for("audience", code=session.code, _external=True)
        img = qrcode.make(qr_url)
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return send_file(buffer, mimetype="image/png", download_name=f"join-{session.code}.png")

    @app.get("/api/sessions")
    def api_sessions():
        return jsonify({"ok": True, "sessions": [serialize_session(item) for item in Session.query.order_by(Session.updated_at.desc())]})

    @app.get("/api/question-templates")
    def api_question_templates():
        return jsonify({"ok": True, "templates": question_templates()})

    @app.post("/api/sessions")
    def api_create_session():
        payload = request.get_json(silent=True) or {}
        try:
            session = Session(title=clean_text(payload.get("title"), 180, required=True), code=generate_session_code())
            db.session.add(session)
            db.session.commit()
            return jsonify({"ok": True, "session": serialize_session(session)}), 201
        except ValueError as exc:
            db.session.rollback()
            return json_error(exc)

    @app.get("/api/sessions/<code>")
    def api_session(code: str):
        session = require_session(code)
        refresh_session_timers(session)
        db.session.commit()
        return jsonify({"ok": True, "session": serialize_session(session)})

    @app.post("/api/sessions/<code>/questions")
    def api_create_question(code: str):
        session = require_session(code)
        try:
            question = add_question(session, request.get_json(silent=True) or {})
            db.session.commit()
            broadcast_session(session)
            return jsonify({"ok": True, "question": serialize_question(question), "session": serialize_session(session)}), 201
        except ValueError as exc:
            db.session.rollback()
            return json_error(exc)

    @app.patch("/api/sessions/<code>/questions/<int:question_id>")
    def api_update_question(code: str, question_id: int):
        session = require_session(code)
        question = require_question(session, question_id)
        try:
            update_question(question, request.get_json(silent=True) or {})
            db.session.commit()
            broadcast_session(session)
            return jsonify({"ok": True, "question": serialize_question(question), "session": serialize_session(session)})
        except ValueError as exc:
            db.session.rollback()
            return json_error(exc)

    @app.post("/api/sessions/<code>/questions/<int:question_id>/duplicate")
    def api_duplicate_question(code: str, question_id: int):
        session = require_session(code)
        question = require_question(session, question_id)
        duplicate = duplicate_question(session, question)
        db.session.commit()
        broadcast_session(session)
        return jsonify({"ok": True, "question": serialize_question(duplicate), "session": serialize_session(session)}), 201

    @app.delete("/api/sessions/<code>/questions/<int:question_id>")
    def api_delete_question(code: str, question_id: int):
        session = require_session(code)
        question = require_question(session, question_id)
        db.session.delete(question)
        db.session.flush()
        normalize_question_positions(session)
        clamp_active_index(session)
        db.session.commit()
        broadcast_session(session)
        return jsonify({"ok": True, "session": serialize_session(session)})

    @app.post("/api/sessions/<code>/questions/reorder")
    def api_reorder_questions(code: str):
        session = require_session(code)
        payload = request.get_json(silent=True) or {}
        try:
            reorder_questions(session, payload.get("question_ids") or [])
            db.session.commit()
            broadcast_session(session)
            return jsonify({"ok": True, "session": serialize_session(session)})
        except ValueError as exc:
            db.session.rollback()
            return json_error(exc)

    @app.post("/api/sessions/<code>/questions/<int:question_id>/responses/<int:response_id>/moderate")
    def api_moderate_response(code: str, question_id: int, response_id: int):
        session = require_session(code)
        question = require_question(session, question_id)
        try:
            response_record = moderate_response(question, response_id, request.get_json(silent=True) or {})
            db.session.commit()
            emit_results(session, question)
            broadcast_session(session)
            return jsonify({"ok": True, "response_id": response_record.id, "results": aggregate_question(question)})
        except ValueError as exc:
            db.session.rollback()
            return json_error(exc)

    @app.get("/api/sessions/<code>/insights")
    def api_session_insights(code: str):
        session = require_session(code)
        refresh_session_timers(session)
        db.session.commit()
        return jsonify({"ok": True, "insights": build_insights(session)})

    @app.get("/api/sessions/<code>/export.csv")
    def export_session_csv(code: str):
        session = require_session(code)
        return send_file(
            build_csv_export(session),
            mimetype="text/csv",
            as_attachment=True,
            download_name=f"mentimeter-{session.code}.csv",
        )

    @app.get("/api/sessions/<code>/export.xlsx")
    def export_session_xlsx(code: str):
        session = require_session(code)
        return send_file(
            build_xlsx_export(session),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"mentimeter-{session.code}.xlsx",
        )

    @app.get("/api/sessions/<code>/export.pdf")
    def export_session_pdf(code: str):
        session = require_session(code)
        return send_file(
            build_pdf_export(session),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"mentimeter-{session.code}.pdf",
        )

    @app.post("/api/sessions/<code>/control")
    def api_control_session(code: str):
        session = require_session(code)
        try:
            apply_control(session, request.get_json(silent=True) or {})
            refresh_session_timers(session)
            db.session.commit()
            broadcast_session(session)
            return jsonify({"ok": True, "session": serialize_session(session)})
        except ValueError as exc:
            db.session.rollback()
            return json_error(exc)

    @app.post("/api/sessions/<code>/questions/<int:question_id>/responses")
    def api_submit_response(code: str, question_id: int):
        session = require_session(code)
        question = require_question(session, question_id)
        participant = get_or_create_participant(session, request.cookies.get(PARTICIPANT_COOKIE))
        try:
            if refresh_session_timers(session):
                db.session.commit()
                broadcast_session(session)
                raise ValueError("Tiempo agotado para esta pregunta.")
            response_record = record_response(session, question, participant, request.get_json(silent=True) or {})
            db.session.commit()
            emit_results(session, question)
            response = jsonify(
                {
                    "ok": True,
                    "participant_token": participant.token,
                    "response_id": response_record.id,
                    "results": aggregate_question(question),
                    "score": participant.score,
                }
            )
            response.set_cookie(PARTICIPANT_COOKIE, participant.token, httponly=True, samesite="Lax")
            return response
        except ValueError as exc:
            db.session.rollback()
            return json_error(exc)


def register_socket_events() -> None:
    @socketio.on("join_session")
    def socket_join_session(data):
        session = find_session((data or {}).get("code"))
        if session is None:
            return {"ok": False, "error": "Sesion no encontrada."}
        refresh_session_timers(session)
        participant = get_or_create_participant(session, (data or {}).get("participant_token"))
        participant.connected = True
        join_room(room_name(session.code))
        socket_participants[request.sid] = (session.id, participant.token)
        db.session.commit()
        emit("participant_count", participant_count(session), to=room_name(session.code))
        return {"ok": True, "session": serialize_session(session), "participant_token": participant.token}

    @socketio.on("submit_response")
    def socket_submit_response(data):
        session = find_session((data or {}).get("code"))
        if session is None:
            return {"ok": False, "error": "Sesion no encontrada."}
        question = db.session.get(Question, int((data or {}).get("question_id") or 0))
        if question is None or question.session_id != session.id:
            return {"ok": False, "error": "Pregunta no encontrada."}
        participant = get_or_create_participant(session, (data or {}).get("participant_token"))
        try:
            if refresh_session_timers(session):
                db.session.commit()
                emit("session_state", serialize_session(session), to=room_name(session.code))
                raise ValueError("Tiempo agotado para esta pregunta.")
            response_record = record_response(session, question, participant, (data or {}).get("payload") or {})
            db.session.commit()
            emit_results(session, question)
            emit("participant_count", participant_count(session), to=room_name(session.code))
            return {
                "ok": True,
                "participant_token": participant.token,
                "response_id": response_record.id,
                "results": aggregate_question(question),
                "score": participant.score,
            }
        except ValueError as exc:
            db.session.rollback()
            return {"ok": False, "error": str(exc)}

    @socketio.on("presenter_control")
    def socket_presenter_control(data):
        session = find_session((data or {}).get("code"))
        if session is None:
            return {"ok": False, "error": "Sesion no encontrada."}
        try:
            apply_control(session, data or {})
            refresh_session_timers(session)
            db.session.commit()
            state = serialize_session(session)
            emit("session_state", state, to=room_name(session.code))
            return {"ok": True, "session": state}
        except ValueError as exc:
            db.session.rollback()
            return {"ok": False, "error": str(exc)}

    @socketio.on("moderate_response")
    def socket_moderate_response(data):
        session = find_session((data or {}).get("code"))
        if session is None:
            return {"ok": False, "error": "Sesion no encontrada."}
        question = db.session.get(Question, int((data or {}).get("question_id") or 0))
        if question is None or question.session_id != session.id:
            return {"ok": False, "error": "Pregunta no encontrada."}
        try:
            response_record = moderate_response(question, int((data or {}).get("response_id") or 0), data or {})
            db.session.commit()
            emit_results(session, question)
            emit("session_state", serialize_session(session), to=room_name(session.code))
            return {"ok": True, "response_id": response_record.id, "results": aggregate_question(question)}
        except ValueError as exc:
            db.session.rollback()
            return {"ok": False, "error": str(exc)}

    @socketio.on("disconnect")
    def socket_disconnect():
        tracked = socket_participants.pop(request.sid, None)
        if not tracked:
            return
        session_id, token = tracked
        participant = Participant.query.filter_by(session_id=session_id, token=token).first()
        if participant:
            participant.connected = False
            db.session.commit()
            emit("participant_count", participant_count(participant.session), to=room_name(participant.session.code))


def add_question(session: Session, payload: dict[str, Any]) -> Question:
    normalized = normalize_question_payload(payload)
    question = Question(
        session=session,
        type=normalized["type"],
        title=normalized["title"],
        prompt=normalized["prompt"],
        position=next_question_position(session),
        config_json=normalized["config"],
        is_open=True,
    )
    db.session.add(question)
    db.session.flush()
    replace_options(question, normalized["options"], normalized.get("correct_option_labels") or [])
    return question


def update_question(question: Question, payload: dict[str, Any]) -> Question:
    merged = {
        "type": payload.get("type", question.type),
        "title": payload.get("title", question.title),
        "prompt": payload.get("prompt", question.prompt),
        "config": {**(question.config_json or {}), **(payload.get("config") or {})},
        "options": payload.get("options", [option.label for option in question.options]),
        "correct_option_labels": payload.get(
            "correct_option_labels",
            [option.label for option in question.options if option.is_correct],
        ),
    }
    normalized = normalize_question_payload(merged)
    question.type = normalized["type"]
    question.title = normalized["title"]
    question.prompt = normalized["prompt"]
    question.config_json = normalized["config"]
    replace_options(question, normalized["options"], normalized.get("correct_option_labels") or [])
    return question


def duplicate_question(session: Session, source: Question) -> Question:
    payload = {
        "type": source.type,
        "title": f"{source.title} (copia)"[:180],
        "prompt": source.prompt,
        "config": dict(source.config_json or {}),
        "options": [option.label for option in source.options],
        "correct_option_labels": [option.label for option in source.options if option.is_correct],
    }
    payload["config"].pop("timer_started_at", None)
    duplicate = add_question(session, payload)
    ordered = sorted(session.questions, key=lambda item: item.position)
    ordered_ids = [question.id for question in ordered if question.id != duplicate.id]
    source_index = ordered_ids.index(source.id)
    ordered_ids.insert(source_index + 1, duplicate.id)
    reorder_questions(session, ordered_ids)
    return duplicate


def normalize_question_payload(payload: dict[str, Any]) -> dict[str, Any]:
    question_type = str(payload.get("type") or "").strip()
    if question_type not in QUESTION_TYPES:
        raise ValueError("Tipo de pregunta no soportado.")
    title = clean_text(payload.get("title"), 180, required=True)
    prompt = clean_text(payload.get("prompt"), 1200, required=True)
    config = dict(payload.get("config") or {})
    options = parse_lines(payload.get("options"))
    correct_labels = set(parse_lines(payload.get("correct_option_labels") or config.get("correct_options")))

    if question_type in {"multiple_choice", "ranking", "quiz"} and len(options) < 2:
        raise ValueError("Agrega al menos dos opciones.")
    if question_type == "quiz" and not correct_labels:
        raise ValueError("Marca al menos una respuesta correcta para el quiz.")
    if question_type == "scale":
        minimum = clamp_int(config.get("min", 1), 1, 10)
        maximum = clamp_int(config.get("max", 5), 2, 10)
        if maximum <= minimum:
            raise ValueError("La escala requiere un maximo mayor al minimo.")
        config = {"min": minimum, "max": maximum}
    elif question_type == "quiz":
        config = {
            "timer_seconds": clamp_int(config.get("timer_seconds", 30), 5, 600),
            "points": clamp_int(config.get("points", 100), 1, 1000),
        }
    elif question_type in {"word_cloud", "open_text"}:
        config = {
            "moderation": normalize_choice(config.get("moderation"), {"none", "manual"}, "none"),
            "show_results": as_bool(config.get("show_results"), True),
        }
    else:
        config = {key: value for key, value in config.items() if key in {"max_entries", "show_results"}}

    return {
        "type": question_type,
        "title": title,
        "prompt": prompt,
        "config": config,
        "options": options,
        "correct_option_labels": correct_labels,
    }


def replace_options(question: Question, labels: list[str], correct_labels: set[str]) -> None:
    for option in list(question.options):
        db.session.delete(option)
    db.session.flush()
    for index, label in enumerate(labels, start=1):
        db.session.add(
            Option(
                question=question,
                label=label,
                position=index,
                is_correct=label in correct_labels,
            )
        )
    db.session.flush()


def record_response(session: Session, question: Question, participant: Participant, payload: dict[str, Any]) -> Response:
    # Single-response questions reuse "default" so a participant edits/replaces the vote instead of duplicating it.
    if session.status != "active":
        raise ValueError("La sesion no esta activa.")
    if session.active_question and session.active_question.id != question.id:
        raise ValueError("Esta no es la pregunta activa.")
    if not question.is_open:
        raise ValueError("La votacion de esta pregunta esta cerrada.")

    normalized = normalize_response_payload(question, payload)
    response_key = "default" if question.type in SINGLE_RESPONSE_TYPES else token_urlsafe(8)
    existing = Response.query.filter_by(question_id=question.id, participant_id=participant.id, response_key=response_key).first()
    if existing and question.type == "quiz":
        participant.score = max(0, participant.score - existing.score_awarded)

    score_awarded = quiz_score(question, normalized) if question.type == "quiz" else 0
    if existing:
        existing.payload_json = normalized
        existing.score_awarded = score_awarded
        existing.is_active = True
        response_record = existing
    else:
        response_record = Response(
            session=session,
            question=question,
            participant=participant,
            response_key=response_key,
            payload_json=normalized,
            score_awarded=score_awarded,
        )
        db.session.add(response_record)

    if question.type == "quiz":
        participant.score += score_awarded
    participant.connected = True
    return response_record


def normalize_response_payload(question: Question, payload: dict[str, Any]) -> dict[str, Any]:
    if question.type in {"multiple_choice", "quiz"}:
        option_id = int(payload.get("option_id") or payload.get("choice") or 0)
        if option_id not in {option.id for option in question.options}:
            raise ValueError("Selecciona una opcion valida.")
        return {"option_id": option_id}
    if question.type == "word_cloud":
        text = clean_text(payload.get("text"), 80, required=True)
        return {"text": text, "status": initial_response_status(question)}
    if question.type == "open_text":
        text = clean_text(payload.get("text"), 500, required=True)
        return {"text": text, "status": initial_response_status(question)}
    if question.type == "scale":
        minimum = int((question.config_json or {}).get("min", 1))
        maximum = int((question.config_json or {}).get("max", 5))
        value = clamp_int(payload.get("value"), minimum, maximum)
        return {"value": value}
    if question.type == "ranking":
        option_ids = [int(value) for value in payload.get("ranking") or []]
        expected = {option.id for option in question.options}
        if set(option_ids) != expected:
            raise ValueError("Ordena todas las opciones del ranking.")
        return {"ranking": option_ids}
    raise ValueError("Tipo de pregunta no soportado.")


def moderate_response(question: Question, response_id: int, payload: dict[str, Any]) -> Response:
    response_record = db.session.get(Response, response_id)
    if response_record is None or response_record.question_id != question.id:
        raise ValueError("Respuesta no encontrada.")
    action = normalize_choice(payload.get("action"), {"approve", "reject"}, "approve")
    next_status = "approved" if action == "approve" else "rejected"
    data = dict(response_record.payload_json or {})
    data["status"] = next_status
    response_record.payload_json = data
    response_record.is_active = next_status != "rejected"
    return response_record


def apply_control(session: Session, payload: dict[str, Any]) -> None:
    action = str(payload.get("action") or "").strip()
    questions = sorted(session.questions, key=lambda item: item.position)
    if action == "start":
        session.status = "active"
        session.active_question_index = min(session.active_question_index, max(len(questions) - 1, 0))
        if session.active_question:
            session.active_question.is_open = True
            start_timer_if_needed(session.active_question)
    elif action == "close":
        session.status = "closed"
        for question in questions:
            question.is_open = False
    elif action == "reset":
        Response.query.filter_by(session_id=session.id).delete()
        for participant in session.participants:
            participant.score = 0
        for question in questions:
            question.is_open = True
            clear_question_timer(question)
        session.status = "draft"
        session.active_question_index = 0
        session.config_json = {**(session.config_json or {}), "theme": (session.config_json or {}).get("theme", "civic")}
    elif action == "next":
        session.active_question_index = min(session.active_question_index + 1, max(len(questions) - 1, 0))
        if session.status == "active" and session.active_question:
            session.active_question.is_open = True
            start_timer_if_needed(session.active_question)
    elif action == "previous":
        session.active_question_index = max(session.active_question_index - 1, 0)
        if session.status == "active" and session.active_question:
            session.active_question.is_open = True
            start_timer_if_needed(session.active_question)
    elif action == "go":
        index = int(payload.get("index") or 0)
        session.active_question_index = min(max(index, 0), max(len(questions) - 1, 0))
        if session.status == "active" and session.active_question:
            session.active_question.is_open = True
            start_timer_if_needed(session.active_question)
    elif action == "close_question":
        if session.active_question:
            session.active_question.is_open = False
    elif action == "open_question":
        if session.active_question:
            session.active_question.is_open = True
            start_timer_if_needed(session.active_question, restart=True)
    elif action == "set_theme":
        theme = normalize_choice(payload.get("theme"), {"civic", "ocean", "contrast"}, "civic")
        config = dict(session.config_json or {})
        config["theme"] = theme
        session.config_json = config
    else:
        raise ValueError("Accion no soportada.")


def aggregate_question(question: Question) -> dict[str, Any]:
    # Results are aggregated on the server so every presenter/audience client receives the same live state.
    responses = [response for response in question.responses if response.is_active]
    if question.type in {"multiple_choice", "quiz"}:
        counts = Counter(int(response.payload_json.get("option_id") or 0) for response in responses)
        return {
            "type": question.type,
            "total": sum(counts.values()),
            "options": [
                {
                    "id": option.id,
                    "label": option.label,
                    "count": counts.get(option.id, 0),
                    "is_correct": option.is_correct,
                }
                for option in question.options
            ],
            "leaderboard": leaderboard(question.session) if question.type == "quiz" else [],
        }
    if question.type == "word_cloud":
        counts = Counter(
            normalize_word(response.payload_json.get("text", ""))
            for response in responses
            if response.payload_json.get("status", "approved") == "approved"
        )
        counts.pop("", None)
        return {
            "type": "word_cloud",
            "total": sum(counts.values()),
            "words": [{"text": text, "count": count} for text, count in counts.most_common(80)],
        }
    if question.type == "open_text":
        visible = [response for response in responses if response.payload_json.get("status", "approved") == "approved"]
        return {
            "type": "open_text",
            "total": len(visible),
            "cards": [
                {"id": response.id, "text": response.payload_json.get("text", "")}
                for response in sorted(visible, key=lambda item: item.created_at, reverse=True)
            ],
        }
    if question.type == "scale":
        values = [int(response.payload_json.get("value") or 0) for response in responses]
        counts = Counter(values)
        minimum = int((question.config_json or {}).get("min", 1))
        maximum = int((question.config_json or {}).get("max", 5))
        return {
            "type": "scale",
            "total": len(values),
            "average": round(sum(values) / len(values), 2) if values else 0,
            "values": [{"value": value, "count": counts.get(value, 0)} for value in range(minimum, maximum + 1)],
        }
    if question.type == "ranking":
        scores: defaultdict[int, int] = defaultdict(int)
        option_count = len(question.options)
        for response in responses:
            for index, option_id in enumerate(response.payload_json.get("ranking") or []):
                scores[int(option_id)] += option_count - index
        return {
            "type": "ranking",
            "total": len(responses),
            "options": [
                {"id": option.id, "label": option.label, "score": scores.get(option.id, 0)}
                for option in question.options
            ],
        }
    return {"type": question.type, "total": len(responses)}


def serialize_session(session: Session) -> dict[str, Any]:
    refresh_session_timers(session)
    active = session.active_question
    return {
        "id": session.id,
        "title": session.title,
        "code": session.code,
        "status": session.status,
        "theme": (session.config_json or {}).get("theme", "civic"),
        "active_question_index": session.active_question_index,
        "active_question_id": active.id if active else None,
        "participant_count": len(session.participants),
        "connected_count": len([participant for participant in session.participants if participant.connected]),
        "join_url": url_for("audience", code=session.code, _external=True),
        "qr_url": url_for("qr_png", code=session.code),
        "questions": [serialize_question(question) for question in sorted(session.questions, key=lambda item: item.position)],
    }


def serialize_question(question: Question) -> dict[str, Any]:
    return {
        "id": question.id,
        "type": question.type,
        "title": question.title,
        "prompt": question.prompt,
        "position": question.position,
        "is_open": question.is_open,
        "config": question.config_json or {},
        "timer": timer_state(question),
        "options": [
            {"id": option.id, "label": option.label, "position": option.position, "is_correct": option.is_correct}
            for option in sorted(question.options, key=lambda item: item.position)
        ],
        "pending_responses": pending_responses(question),
        "results": aggregate_question(question),
    }


def ensure_demo_session() -> Session:
    # Idempotent seed: keeps local startup friendly without overwriting user-created sessions.
    session = Session.query.filter_by(code="123456").first()
    if session:
        return session
    session = Session(title="Demo participativa", code="123456", status="draft")
    db.session.add(session)
    db.session.flush()
    add_question(
        session,
        {
            "type": "multiple_choice",
            "title": "Prioridad del taller",
            "prompt": "Que tema deberiamos atender primero?",
            "options": ["Atencion ciudadana", "Procesos internos", "Datos y reportes", "Coordinacion"],
        },
    )
    add_question(
        session,
        {
            "type": "word_cloud",
            "title": "Una palabra",
            "prompt": "Describe el reto principal en una palabra.",
        },
    )
    add_question(
        session,
        {
            "type": "quiz",
            "title": "Quiz rapido",
            "prompt": "Que herramienta permite actualizaciones en tiempo real?",
            "options": ["CSV", "WebSockets", "PDF", "Correo"],
            "correct_option_labels": ["WebSockets"],
            "config": {"timer_seconds": 30, "points": 100},
        },
    )
    db.session.commit()
    return session


def question_templates() -> list[dict[str, Any]]:
    return [
        {
            "name": "Pulso de prioridad",
            "payload": {
                "type": "multiple_choice",
                "title": "Pulso de prioridad",
                "prompt": "Que tema merece atencion inmediata?",
                "options": ["Atencion ciudadana", "Eficiencia interna", "Transparencia", "Coordinacion"],
            },
        },
        {
            "name": "Lluvia con moderacion",
            "payload": {
                "type": "word_cloud",
                "title": "Lluvia de ideas",
                "prompt": "Escribe una palabra clave para el diagnostico.",
                "config": {"moderation": "manual"},
            },
        },
        {
            "name": "Escala 1 a 10",
            "payload": {
                "type": "scale",
                "title": "Nivel de acuerdo",
                "prompt": "Califica del 1 al 10.",
                "config": {"min": 1, "max": 10},
            },
        },
        {
            "name": "Quiz rapido",
            "payload": {
                "type": "quiz",
                "title": "Quiz rapido",
                "prompt": "Selecciona la respuesta correcta.",
                "options": ["Opcion A", "Opcion B", "Opcion C"],
                "correct_option_labels": ["Opcion B"],
                "config": {"timer_seconds": 30, "points": 100},
            },
        },
    ]


def refresh_session_timers(session: Session) -> bool:
    changed = False
    if session.status != "active":
        return changed
    for question in session.questions:
        if question.type == "quiz" and question.is_open and timer_remaining(question) == 0:
            question.is_open = False
            changed = True
    return changed


def start_timer_if_needed(question: Question, *, restart: bool = False) -> None:
    if question.type != "quiz":
        return
    config = dict(question.config_json or {})
    if restart or not config.get("timer_started_at"):
        config["timer_started_at"] = utcnow().isoformat()
        question.config_json = config


def clear_question_timer(question: Question) -> None:
    if question.type != "quiz":
        return
    config = dict(question.config_json or {})
    config.pop("timer_started_at", None)
    question.config_json = config


def timer_remaining(question: Question) -> int | None:
    if question.type != "quiz":
        return None
    config = question.config_json or {}
    duration = int(config.get("timer_seconds") or 30)
    started_at = parse_datetime(config.get("timer_started_at"))
    if not started_at:
        return duration
    elapsed = int((utcnow() - started_at).total_seconds())
    return max(0, duration - elapsed)


def timer_state(question: Question) -> dict[str, Any] | None:
    if question.type != "quiz":
        return None
    config = question.config_json or {}
    return {
        "duration": int(config.get("timer_seconds") or 30),
        "started_at": config.get("timer_started_at"),
        "remaining": timer_remaining(question),
    }


def pending_responses(question: Question) -> list[dict[str, Any]]:
    if question.type not in {"word_cloud", "open_text"}:
        return []
    return [
        {"id": response.id, "text": response.payload_json.get("text", ""), "status": response.payload_json.get("status", "approved")}
        for response in question.responses
        if response.payload_json.get("status") == "pending"
    ]


def initial_response_status(question: Question) -> str:
    return "pending" if (question.config_json or {}).get("moderation") == "manual" else "approved"


def build_insights(session: Session) -> dict[str, Any]:
    refresh_session_timers(session)
    questions = sorted(session.questions, key=lambda item: item.position)
    return {
        "code": session.code,
        "title": session.title,
        "status": session.status,
        "theme": (session.config_json or {}).get("theme", "civic"),
        "question_count": len(questions),
        "participant_count": len(session.participants),
        "response_count": len(session.responses),
        "active_question": session.active_question.title if session.active_question else None,
        "questions": [
            {
                "id": question.id,
                "title": question.title,
                "type": question.type,
                "response_count": len([response for response in question.responses if response.is_active]),
                "results": aggregate_question(question),
            }
            for question in questions
        ],
    }


def export_rows(session: Session) -> list[list[Any]]:
    rows: list[list[Any]] = [["session_code", "question", "type", "participant_id", "response", "score_awarded", "created_at"]]
    for question in sorted(session.questions, key=lambda item: item.position):
        for response in question.responses:
            rows.append(
                [
                    session.code,
                    question.title,
                    question.type,
                    response.participant_id,
                    json.dumps(response.payload_json, ensure_ascii=False),
                    response.score_awarded,
                    response.created_at.isoformat() if response.created_at else "",
                ]
            )
    return rows


def build_csv_export(session: Session) -> BytesIO:
    text_buffer = StringIO()
    writer = csv.writer(text_buffer)
    writer.writerows(export_rows(session))
    buffer = BytesIO(text_buffer.getvalue().encode("utf-8-sig"))
    buffer.seek(0)
    return buffer


def build_xlsx_export(session: Session) -> BytesIO:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Respuestas"
    for row in export_rows(session):
        sheet.append(row)
    summary = workbook.create_sheet("Insights")
    insights = build_insights(session)
    for key in ["code", "title", "status", "question_count", "participant_count", "response_count"]:
        summary.append([key, insights[key]])
    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer


def build_pdf_export(session: Session) -> BytesIO:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 54
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(54, y, f"Resultados {session.title}")
    y -= 24
    pdf.setFont("Helvetica", 10)
    pdf.drawString(54, y, f"Codigo: {session.code} | Participantes: {len(session.participants)} | Respuestas: {len(session.responses)}")
    y -= 30
    for question in sorted(session.questions, key=lambda item: item.position):
        if y < 120:
            pdf.showPage()
            y = height - 54
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(54, y, f"{question.position}. {question.title} ({question.type})")
        y -= 16
        pdf.setFont("Helvetica", 9)
        results = aggregate_question(question)
        for line in json.dumps(results, ensure_ascii=False)[:1000].split(","):
            if y < 54:
                pdf.showPage()
                y = height - 54
            pdf.drawString(64, y, line[:105])
            y -= 12
        y -= 8
    pdf.save()
    buffer.seek(0)
    return buffer


def find_session(code: str | None) -> Session | None:
    normalized = "".join(ch for ch in str(code or "") if ch.isdigit())[:6]
    if len(normalized) != 6:
        return None
    return Session.query.filter_by(code=normalized).first()


def require_session(code: str) -> Session:
    session = find_session(code)
    if session is None:
        abort(404)
    return session


def require_question(session: Session, question_id: int) -> Question:
    question = db.session.get(Question, question_id)
    if question is None or question.session_id != session.id:
        abort(404)
    return question


def get_or_create_participant(session: Session, token: str | None) -> Participant:
    participant = None
    if token:
        participant = Participant.query.filter_by(session_id=session.id, token=token).first()
    if participant is None:
        participant = Participant(session=session, token=token or token_urlsafe(32), connected=True)
        db.session.add(participant)
        db.session.flush()
    participant.connected = True
    return participant


def generate_session_code() -> str:
    for _ in range(100):
        code = f"{randint(0, 999999):06d}"
        if Session.query.filter_by(code=code).first() is None:
            return code
    raise ValueError("No se pudo generar un codigo unico.")


def next_question_position(session: Session) -> int:
    return max([question.position for question in session.questions] or [0]) + 1


def normalize_question_positions(session: Session) -> None:
    for index, question in enumerate(sorted(session.questions, key=lambda item: item.position), start=1):
        question.position = index


def reorder_questions(session: Session, question_ids: list[Any]) -> None:
    ordered_ids = [int(value) for value in question_ids]
    questions = sorted(session.questions, key=lambda item: item.position)
    existing_ids = [question.id for question in questions]
    if sorted(ordered_ids) != sorted(existing_ids):
        raise ValueError("El orden no coincide con las preguntas de la sesion.")
    by_id = {question.id: question for question in questions}
    for index, question_id in enumerate(ordered_ids, start=1):
        by_id[question_id].position = -index
    db.session.flush()
    for index, question_id in enumerate(ordered_ids, start=1):
        by_id[question_id].position = index
    clamp_active_index(session)


def clamp_active_index(session: Session) -> None:
    session.active_question_index = min(max(session.active_question_index, 0), max(len(session.questions) - 1, 0))


def room_name(code: str) -> str:
    return f"session:{code}"


def participant_count(session: Session) -> dict[str, int | str]:
    return {
        "code": session.code,
        "participant_count": len(session.participants),
        "connected_count": len([participant for participant in session.participants if participant.connected]),
    }


def broadcast_session(session: Session) -> None:
    socketio.emit("session_state", serialize_session(session), to=room_name(session.code))


def emit_results(session: Session, question: Question) -> None:
    socketio.emit(
        "results_updated",
        {"code": session.code, "question_id": question.id, "results": aggregate_question(question)},
        to=room_name(session.code),
    )


def quiz_score(question: Question, payload: dict[str, Any]) -> int:
    correct_ids = {option.id for option in question.options if option.is_correct}
    if int(payload.get("option_id") or 0) in correct_ids:
        return int((question.config_json or {}).get("points") or 100)
    return 0


def leaderboard(session: Session) -> list[dict[str, Any]]:
    ordered = sorted(session.participants, key=lambda item: item.score, reverse=True)
    return [
        {"participant_id": participant.id, "label": f"Participante {index}", "score": participant.score}
        for index, participant in enumerate(ordered[:10], start=1)
        if participant.score > 0
    ]


def clean_text(value: Any, max_length: int, *, required: bool = False) -> str:
    text = str(value or "").strip()
    if required and len(text) < 1:
        raise ValueError("Captura el texto requerido.")
    if len(text) > max_length:
        raise ValueError(f"El texto no puede superar {max_length} caracteres.")
    return text


def parse_lines(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = str(value).replace("\r", "\n").split("\n")
    items = []
    for item in raw_items:
        text = clean_text(item, 180)
        if text and text not in items:
            items.append(text)
    return items[:12]


def clamp_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = minimum
    return min(max(number, minimum), maximum)


def as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "on", "yes", "si"}


def normalize_choice(value: Any, allowed: set[str], default: str) -> str:
    text = str(value or "").strip()
    return text if text in allowed else default


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def normalize_word(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def json_error(exc: Exception, status_code: int = 400):
    return jsonify({"ok": False, "error": str(exc)}), status_code


app = create_app()


if __name__ == "__main__":
    socketio.run(app, host="127.0.0.1", port=5000, debug=True)
