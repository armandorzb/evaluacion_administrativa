from __future__ import annotations

from pydantic import ValidationError

from flask import Blueprint, abort, flash, jsonify, make_response, redirect, render_template, request, send_file, url_for
from flask_login import current_user

from municipal_diagnostico.decorators import live_role_required
from municipal_diagnostico.extensions import db, socketio
from municipal_diagnostico.live.services import (
    LIVE_PARTICIPANT_COOKIE,
    LiveValidationError,
    add_activity,
    aggregate_results,
    apply_presenter_control,
    build_live_excel,
    build_live_pdf,
    build_qr_data_uri,
    build_qr_png,
    create_session,
    create_template,
    find_session_by_code,
    get_or_create_participant,
    moderate_response,
    room_name,
    serialize_activity,
    serialize_session,
    submit_response,
    update_template,
    upvote_response,
)
from municipal_diagnostico.models import LiveActivity, LiveReactivoTemplate, LiveSession
from municipal_diagnostico.services.activity_logger import log_activity


bp = Blueprint("live", __name__, url_prefix="/live")

ACTIVITY_TYPE_LABELS = {
    "brainstorm": "Lluvia de ideas",
    "multiple_choice": "Opcion multiple",
    "scale": "Escala",
    "ranking": "Ranking",
    "points_100": "100 puntos",
    "matrix_2x2": "Matriz 2x2",
    "qa": "Q&A",
    "quiz_choice": "Quiz opcion",
    "quiz_text": "Quiz texto",
}


@bp.app_context_processor
def live_template_helpers():
    return {"live_type_label": lambda tipo: ACTIVITY_TYPE_LABELS.get(tipo, tipo)}


@bp.route("/")
@live_role_required("administrador", "consulta")
def dashboard():
    sessions = LiveSession.query.order_by(LiveSession.updated_at.desc()).limit(6).all()
    templates = LiveReactivoTemplate.query.order_by(LiveReactivoTemplate.updated_at.desc()).limit(6).all()
    log_activity("view_live_dashboard", metadata={"modulo": "live"})
    return render_template(
        "live/dashboard.html",
        sessions=sessions,
        templates=templates,
        counts={
            "templates": LiveReactivoTemplate.query.count(),
            "sessions": LiveSession.query.count(),
            "active_sessions": LiveSession.query.filter_by(estado="active").count(),
        },
    )


@bp.route("/templates", methods=["GET", "POST"])
@live_role_required("administrador", "consulta")
def templates():
    if request.method == "POST":
        require_live_admin()
        action = request.form.get("action") or "create"
        try:
            if action == "create":
                template = create_template(template_payload_from_form(request.form), current_user)
                db.session.commit()
                log_activity("create_live_template", entity_type="live_reactivo_template", entity_id=template.id)
                flash("Reactivo live creado.", "success")
            elif action == "update":
                template = LiveReactivoTemplate.query.get_or_404(request.form.get("template_id", type=int))
                update_template(template, template_payload_from_form(request.form))
                db.session.commit()
                log_activity("update_live_template", entity_type="live_reactivo_template", entity_id=template.id)
                flash("Reactivo live actualizado.", "success")
            elif action == "toggle":
                template = LiveReactivoTemplate.query.get_or_404(request.form.get("template_id", type=int))
                template.activo = not template.activo
                db.session.commit()
                log_activity("toggle_live_template", entity_type="live_reactivo_template", entity_id=template.id)
                flash("Estado del reactivo actualizado.", "success")
        except (ValidationError, ValueError, LiveValidationError) as exc:
            db.session.rollback()
            flash(validation_message(exc), "error")
        return redirect(url_for("live.templates"))

    return render_template(
        "live/templates.html",
        templates=LiveReactivoTemplate.query.order_by(LiveReactivoTemplate.updated_at.desc()).all(),
    )


@bp.route("/sessions", methods=["GET", "POST"])
@live_role_required("administrador", "consulta")
def sessions():
    if request.method == "POST":
        require_live_admin()
        try:
            session = create_session(session_payload_from_form(request.form), current_user)
            db.session.commit()
            log_activity("create_live_session", entity_type="live_session", entity_id=session.id)
            flash("Sesión live creada.", "success")
            return redirect(url_for("live.session_detail", session_id=session.id))
        except (ValidationError, ValueError, LiveValidationError) as exc:
            db.session.rollback()
            flash(validation_message(exc), "error")
            return redirect(url_for("live.sessions"))

    return render_template(
        "live/sessions.html",
        sessions=LiveSession.query.order_by(LiveSession.updated_at.desc()).all(),
        templates=LiveReactivoTemplate.query.filter_by(activo=True).order_by(LiveReactivoTemplate.titulo).all(),
    )


@bp.route("/sessions/<int:session_id>", methods=["GET", "POST"])
@live_role_required("administrador", "consulta")
def session_detail(session_id: int):
    session = LiveSession.query.get_or_404(session_id)
    if request.method == "POST":
        require_live_admin()
        try:
            activity = add_activity(session, activity_payload_from_form(request.form))
            db.session.commit()
            log_activity("add_live_activity", entity_type="live_activity", entity_id=activity.id)
            flash("Actividad agregada a la sesión.", "success")
        except (ValidationError, ValueError, LiveValidationError) as exc:
            db.session.rollback()
            flash(validation_message(exc), "error")
        return redirect(url_for("live.session_detail", session_id=session.id))

    join_url = url_for("live.public_session", code=session.code, _external=True)
    qr_access_url = url_for("live.qr_redirect", code=session.code, _external=True)
    return render_template(
        "live/session_detail.html",
        session=session,
        templates=LiveReactivoTemplate.query.filter_by(activo=True).order_by(LiveReactivoTemplate.titulo).all(),
        join_url=join_url,
        qr_access_url=qr_access_url,
        qr_image_url=url_for("live.session_qr_png", code=session.code),
        qr_data_uri=build_qr_data_uri(qr_access_url),
    )


@bp.route("/sessions/<int:session_id>/present")
@live_role_required("administrador", "consulta")
def present(session_id: int):
    session = LiveSession.query.get_or_404(session_id)
    join_url = url_for("live.public_session", code=session.code, _external=True)
    qr_access_url = url_for("live.qr_redirect", code=session.code, _external=True)
    log_activity("view_live_presenter", entity_type="live_session", entity_id=session.id)
    return render_template(
        "live/present.html",
        session=session,
        session_state=serialize_session(session),
        join_url=join_url,
        qr_access_url=qr_access_url,
        qr_image_url=url_for("live.session_qr_png", code=session.code),
        qr_data_uri=build_qr_data_uri(qr_access_url),
    )


@bp.route("/sessions/<int:session_id>/instructions")
@live_role_required("administrador", "consulta")
def instructions(session_id: int):
    session = LiveSession.query.get_or_404(session_id)
    join_url = url_for("live.public_session", code=session.code, _external=True)
    qr_access_url = url_for("live.qr_redirect", code=session.code, _external=True)
    return render_template(
        "live/instructions.html",
        session=session,
        join_url=join_url,
        qr_access_url=qr_access_url,
        qr_image_url=url_for("live.session_qr_png", code=session.code),
        qr_data_uri=build_qr_data_uri(qr_access_url),
    )


@bp.route("/sessions/<int:session_id>/export.xlsx")
@live_role_required("administrador", "consulta")
def export_session_xlsx(session_id: int):
    session = LiveSession.query.get_or_404(session_id)
    buffer = build_live_excel(session)
    log_activity("export_live_xlsx", entity_type="live_session", entity_id=session.id)
    return send_file(
        buffer,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"live-{session.code}.xlsx",
    )


@bp.route("/sessions/<int:session_id>/export.pdf")
@live_role_required("administrador", "consulta")
def export_session_pdf(session_id: int):
    session = LiveSession.query.get_or_404(session_id)
    buffer = build_live_pdf(session)
    log_activity("export_live_pdf", entity_type="live_session", entity_id=session.id)
    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"live-{session.code}.pdf",
    )


@bp.route("/sessions/<int:session_id>/control", methods=["POST"])
@live_role_required("administrador")
def control_session(session_id: int):
    session = LiveSession.query.get_or_404(session_id)
    payload = {
        "session_id": session.id,
        "action": request.form.get("action"),
        "activity_id": request.form.get("activity_id", type=int),
        "response_id": request.form.get("response_id", type=int),
        "mode": request.form.get("mode"),
        "timer_seconds": request.form.get("timer_seconds", type=int),
    }
    try:
        apply_presenter_control(session, payload)
        db.session.commit()
        broadcast_session(session)
        log_activity("control_live_session", entity_type="live_session", entity_id=session.id, metadata={"action": payload["action"]})
        flash("Sesión actualizada.", "success")
    except (ValidationError, ValueError, LiveValidationError) as exc:
        db.session.rollback()
        flash(validation_message(exc), "error")
    return redirect(request.referrer or url_for("live.session_detail", session_id=session.id))


@bp.route("/join", methods=["GET", "POST"])
def join():
    code = request.values.get("code") or request.values.get("codigo")
    if request.method == "POST" or code:
        session = find_session_by_code(code)
        if session is None:
            flash("No encontramos una sesión con ese código.", "error")
            return redirect(url_for("live.join"))
        return redirect(url_for("live.public_session", code=session.code))
    return render_template("live/join.html")


@bp.route("/q/<string:code>")
def qr_redirect(code: str):
    session = find_session_by_code(code)
    if session is None:
        abort(404)
    return redirect(url_for("live.public_session", code=session.code))


@bp.route("/qr/<string:code>.png")
def session_qr_png(code: str):
    session = find_session_by_code(code)
    if session is None:
        abort(404)
    qr_access_url = url_for("live.qr_redirect", code=session.code, _external=True)
    return send_file(
        build_qr_png(qr_access_url),
        mimetype="image/png",
        download_name=f"live-{session.code}-qr.png",
        max_age=300,
    )


@bp.route("/s/<string:code>")
def public_session(code: str):
    session = find_session_by_code(code)
    if session is None:
        abort(404)
    participant = get_or_create_participant(session, request.cookies.get(LIVE_PARTICIPANT_COOKIE))
    db.session.commit()
    response = make_response(render_public_session(session, participant=participant))
    attach_participant_cookie(response, participant)
    return response


@bp.route("/s/<string:code>/activity/<int:activity_id>")
def public_activity(code: str, activity_id: int):
    session = find_session_by_code(code)
    if session is None:
        abort(404)
    activity = db.session.get(LiveActivity, activity_id)
    if activity is None or activity.session_id != session.id:
        abort(404)
    participant = get_or_create_participant(session, request.cookies.get(LIVE_PARTICIPANT_COOKIE))
    db.session.commit()
    response = make_response(render_public_session(session, activity=activity, participant=participant))
    attach_participant_cookie(response, participant)
    return response


@bp.route("/api/templates", methods=["POST"])
@live_role_required("administrador")
def api_create_template():
    try:
        template = create_template(request.get_json(silent=True) or {}, current_user)
        db.session.commit()
        return jsonify({"ok": True, "template": serialize_template(template)}), 201
    except (ValidationError, ValueError, LiveValidationError) as exc:
        db.session.rollback()
        return json_error(exc)


@bp.route("/api/sessions", methods=["POST"])
@live_role_required("administrador")
def api_create_session():
    try:
        session = create_session(request.get_json(silent=True) or {}, current_user)
        db.session.commit()
        return jsonify({"ok": True, "session": serialize_session(session)}), 201
    except (ValidationError, ValueError, LiveValidationError) as exc:
        db.session.rollback()
        return json_error(exc)


@bp.route("/api/sessions/<int:session_id>/activities", methods=["POST"])
@live_role_required("administrador")
def api_add_activity(session_id: int):
    session = LiveSession.query.get_or_404(session_id)
    try:
        activity = add_activity(session, request.get_json(silent=True) or {})
        db.session.commit()
        broadcast_session(session)
        return jsonify({"ok": True, "activity": serialize_activity(activity)}), 201
    except (ValidationError, ValueError, LiveValidationError) as exc:
        db.session.rollback()
        return json_error(exc)


@bp.route("/api/sessions/<int:session_id>/control", methods=["POST"])
@live_role_required("administrador")
def api_control_session(session_id: int):
    session = LiveSession.query.get_or_404(session_id)
    payload = request.get_json(silent=True) or {}
    payload["session_id"] = session.id
    try:
        apply_presenter_control(session, payload)
        db.session.commit()
        broadcast_session(session)
        return jsonify({"ok": True, "session": serialize_session(session)})
    except (ValidationError, ValueError, LiveValidationError) as exc:
        db.session.rollback()
        return json_error(exc)


@bp.route("/api/sessions/<int:session_id>/state")
@live_role_required("administrador", "consulta")
def api_session_state(session_id: int):
    session = LiveSession.query.get_or_404(session_id)
    return jsonify({"ok": True, "session": serialize_session(session)})


@bp.route("/api/s/<string:code>/activities/<int:activity_id>/responses", methods=["POST"])
def api_submit_public_response(code: str, activity_id: int):
    session = find_session_by_code(code)
    if session is None:
        abort(404)
    activity = db.session.get(LiveActivity, activity_id)
    if activity is None or activity.session_id != session.id:
        abort(404)
    token = request.cookies.get(LIVE_PARTICIPANT_COOKIE)
    participant = get_or_create_participant(session, token)
    raw = request.get_json(silent=True) or {}
    try:
        response_record = submit_response(session, activity, participant, raw.get("payload") or raw)
        db.session.commit()
        broadcast_results(session, activity)
        response = jsonify(
            {
                "ok": True,
                "response_id": response_record.id,
                "participant_token": participant.token,
                "results": aggregate_results(activity),
            }
        )
        response.set_cookie(LIVE_PARTICIPANT_COOKIE, participant.token, httponly=True, samesite="Lax")
        return response
    except (ValidationError, ValueError, LiveValidationError) as exc:
        db.session.rollback()
        return json_error(exc)


@bp.route("/api/sessions/<int:session_id>/activities/<int:activity_id>/responses/<int:response_id>/moderate", methods=["POST"])
@live_role_required("administrador")
def api_moderate_response(session_id: int, activity_id: int, response_id: int):
    session = LiveSession.query.get_or_404(session_id)
    activity = db.session.get(LiveActivity, activity_id)
    if activity is None or activity.session_id != session.id:
        abort(404)
    payload = request.get_json(silent=True) or request.form
    try:
        response_record = moderate_response(session, activity, response_id, str(payload.get("action") or "approve"))
        db.session.commit()
        broadcast_results(session, activity)
        broadcast_session(session)
        log_activity(
            "moderate_live_response",
            entity_type="live_response",
            entity_id=response_record.id,
            metadata={"action": payload.get("action")},
        )
        return jsonify({"ok": True, "response_id": response_record.id, "results": aggregate_results(activity)})
    except (ValidationError, ValueError, LiveValidationError) as exc:
        db.session.rollback()
        return json_error(exc)


@bp.route("/api/s/<string:code>/activities/<int:activity_id>/responses/<int:response_id>/upvote", methods=["POST"])
def api_upvote_public_response(code: str, activity_id: int, response_id: int):
    session = find_session_by_code(code)
    if session is None:
        abort(404)
    activity = db.session.get(LiveActivity, activity_id)
    if activity is None or activity.session_id != session.id:
        abort(404)
    participant = get_or_create_participant(session, request.cookies.get(LIVE_PARTICIPANT_COOKIE))
    try:
        response_record = upvote_response(session, activity, response_id, participant)
        db.session.commit()
        broadcast_results(session, activity)
        response = jsonify({"ok": True, "response_id": response_record.id, "results": aggregate_results(activity)})
        response.set_cookie(LIVE_PARTICIPANT_COOKIE, participant.token, httponly=True, samesite="Lax")
        return response
    except (ValidationError, ValueError, LiveValidationError) as exc:
        db.session.rollback()
        return json_error(exc)


def render_public_session(session: LiveSession, *, participant, activity: LiveActivity | None = None):
    if activity is None and session.mode == "guided" and session.active_activity_id:
        activity = db.session.get(LiveActivity, session.active_activity_id)
    open_activities = [item for item in session.activities if item.estado == "open"]
    return render_template(
        "live/participant.html",
        session=session,
        activity=activity,
        activities=open_activities,
        participant=participant,
        session_state=serialize_session(session),
        activity_state=serialize_activity(activity) if activity else None,
    )


def attach_participant_cookie(response, participant) -> None:
    response.set_cookie(LIVE_PARTICIPANT_COOKIE, participant.token, httponly=True, samesite="Lax")


def require_live_admin() -> None:
    if current_user.rol != "administrador":
        abort(403)


def template_payload_from_form(form) -> dict[str, object]:
    tipo = (form.get("tipo") or "").strip()
    config: dict[str, object] = {
        "show_results": form_bool(form, "show_results", default=True),
        "result_layout": form.get("result_layout") or "chart",
    }
    if tipo == "brainstorm":
        config.update(
            {
                "max_ideas_per_participant": form.get("max_ideas_per_participant"),
                "max_length": form.get("max_length"),
                "moderation": form.get("moderation") or "none",
            }
        )
    elif tipo == "multiple_choice":
        config.update({"options": form.get("options") or ""})
    elif tipo == "scale":
        config.update(
            {
                "items": form.get("items") or "",
                "min": form.get("min"),
                "max": form.get("max"),
                "min_label": form.get("min_label"),
                "max_label": form.get("max_label"),
                "allow_skip": form_bool(form, "allow_skip"),
            }
        )
    elif tipo == "ranking":
        config.update({"items": form.get("items") or "", "max_ranked": form.get("max_ranked")})
    elif tipo == "points_100":
        config.update(
            {
                "items": form.get("items") or "",
                "total_points": form.get("total_points"),
                "step": form.get("step"),
            }
        )
    elif tipo == "matrix_2x2":
        config.update(
            {
                "items": form.get("items") or "",
                "min": form.get("min"),
                "max": form.get("max"),
                "x_axis": {"min_label": form.get("x_min_label"), "max_label": form.get("x_max_label")},
                "y_axis": {"min_label": form.get("y_min_label"), "max_label": form.get("y_max_label")},
                "quadrants": form.get("quadrants") or "",
            }
        )
    elif tipo == "qa":
        config.update(
            {
                "moderation": form.get("moderation") or "manual",
                "allow_upvotes": form_bool(form, "allow_upvotes", default=True),
                "visibility": form.get("visibility") or "approved",
                "global_scope": form_bool(form, "global_scope"),
                "max_length": form.get("max_length"),
            }
        )
    elif tipo == "quiz_choice":
        config.update(
            {
                "options": form.get("options") or "",
                "correct_options": form.get("correct_options") or "",
                "timer_seconds": form.get("timer_seconds"),
                "points": form.get("points"),
            }
        )
    elif tipo == "quiz_text":
        config.update(
            {
                "answers": form.get("answers") or "",
                "timer_seconds": form.get("timer_seconds"),
                "points": form.get("points"),
                "case_sensitive": form_bool(form, "case_sensitive"),
            }
        )
    return {
        "tipo": tipo,
        "titulo": form.get("titulo") or "",
        "prompt": form.get("prompt") or "",
        "config": config,
    }


def session_payload_from_form(form) -> dict[str, object]:
    return {
        "titulo": form.get("titulo") or "",
        "descripcion": form.get("descripcion") or None,
        "mode": form.get("mode") or "guided",
        "template_ids": [int(value) for value in form.getlist("template_ids") if str(value).isdigit()],
    }


def activity_payload_from_form(form) -> dict[str, object]:
    template_id = form.get("template_id", type=int)
    if template_id:
        return {"template_id": template_id}
    return template_payload_from_form(form)


def form_bool(form, name: str, *, default: bool = False) -> bool:
    if name not in form:
        return default
    return str(form.get(name) or "").lower() in {"1", "true", "on", "yes", "si"}


def serialize_template(template: LiveReactivoTemplate) -> dict[str, object]:
    return {
        "id": template.id,
        "tipo": template.tipo,
        "titulo": template.titulo,
        "prompt": template.prompt,
        "config": template.config_json or {},
        "activo": template.activo,
    }


def broadcast_session(session: LiveSession) -> None:
    socketio.emit("live:session_state", serialize_session(session), to=room_name(session.id))
    for activity in session.activities:
        socketio.emit("live:activity_state", serialize_activity(activity), to=room_name(session.id))


def broadcast_results(session: LiveSession, activity: LiveActivity) -> None:
    socketio.emit(
        "live:results_updated",
        {"session_id": session.id, "activity_id": activity.id, "results": aggregate_results(activity)},
        to=room_name(session.id),
    )


def validation_message(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        return str(first.get("msg") or "Datos inválidos.")
    return str(exc)


def json_error(exc: Exception, status_code: int = 400):
    return jsonify({"ok": False, "error": validation_message(exc)}), status_code
