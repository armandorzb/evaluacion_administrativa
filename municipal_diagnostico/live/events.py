from __future__ import annotations

from pydantic import ValidationError

from flask_login import current_user
from flask_socketio import emit, join_room

from municipal_diagnostico.extensions import db
from municipal_diagnostico.live.services import (
    LiveValidationError,
    aggregate_results,
    apply_presenter_control,
    find_session_by_code,
    get_or_create_participant,
    mark_participant_seen,
    moderate_response,
    room_name,
    serialize_activity,
    serialize_session,
    submit_response,
    upvote_response,
)
from municipal_diagnostico.models import LiveActivity, LiveSession


def register_socketio_events(socketio) -> None:
    @socketio.on("live:join_session")
    def join_live_session(data):
        session = resolve_session(data or {})
        if session is None:
            return {"ok": False, "error": "Sesión no encontrada."}

        join_room(room_name(session.id))
        token = (data or {}).get("participant_token")
        if token:
            mark_participant_seen(session, token, connected=True)
            db.session.commit()

        emit("live:participant_count", participant_count_payload(session), to=room_name(session.id))
        return {"ok": True, "session": serialize_session(session)}

    @socketio.on("live:participant_seen")
    def participant_seen(data):
        session = resolve_session(data or {})
        if session is None:
            return {"ok": False, "error": "Sesión no encontrada."}
        participant = mark_participant_seen(session, (data or {}).get("participant_token"), connected=True)
        db.session.commit()
        emit("live:participant_count", participant_count_payload(session), to=room_name(session.id))
        return {"ok": True, "participant_token": participant.token}

    @socketio.on("live:submit_response")
    def socket_submit_response(data):
        session = resolve_session(data or {})
        if session is None:
            return {"ok": False, "error": "Sesión no encontrada."}
        activity = db.session.get(LiveActivity, int((data or {}).get("activity_id") or 0))
        if activity is None or activity.session_id != session.id:
            return {"ok": False, "error": "Actividad no encontrada."}

        try:
            participant = get_or_create_participant(session, (data or {}).get("participant_token"))
            response = submit_response(session, activity, participant, (data or {}).get("payload") or {})
            db.session.commit()
            payload = {"session_id": session.id, "activity_id": activity.id, "results": aggregate_results(activity)}
            emit("live:results_updated", payload, to=room_name(session.id))
            emit("live:participant_count", participant_count_payload(session), to=room_name(session.id))
            return {"ok": True, "response_id": response.id, "participant_token": participant.token, "results": payload["results"]}
        except (ValidationError, ValueError, LiveValidationError) as exc:
            db.session.rollback()
            return {"ok": False, "error": validation_message(exc)}

    @socketio.on("live:upvote_response")
    def socket_upvote_response(data):
        session = resolve_session(data or {})
        if session is None:
            return {"ok": False, "error": "Sesion no encontrada."}
        activity = db.session.get(LiveActivity, int((data or {}).get("activity_id") or 0))
        if activity is None or activity.session_id != session.id:
            return {"ok": False, "error": "Actividad no encontrada."}
        response_id = int((data or {}).get("response_id") or 0)
        try:
            participant = get_or_create_participant(session, (data or {}).get("participant_token"))
            response = upvote_response(session, activity, response_id, participant)
            db.session.commit()
            payload = {"session_id": session.id, "activity_id": activity.id, "results": aggregate_results(activity)}
            emit("live:results_updated", payload, to=room_name(session.id))
            return {"ok": True, "response_id": response.id, "participant_token": participant.token, "results": payload["results"]}
        except (ValidationError, ValueError, LiveValidationError) as exc:
            db.session.rollback()
            return {"ok": False, "error": validation_message(exc)}

    @socketio.on("live:presenter_control")
    def socket_presenter_control(data):
        if not current_user.is_authenticated or not getattr(current_user, "puede_acceder_live", False):
            return {"ok": False, "error": "No tienes acceso a Live."}
        if current_user.rol != "administrador":
            return {"ok": False, "error": "Solo administradores pueden controlar la sesión."}

        session = resolve_session(data or {})
        if session is None:
            return {"ok": False, "error": "Sesión no encontrada."}

        payload = dict(data or {})
        payload["session_id"] = session.id
        try:
            apply_presenter_control(session, payload)
            db.session.commit()
            state = serialize_session(session)
            emit("live:session_state", state, to=room_name(session.id))
            for activity in session.activities:
                emit("live:activity_state", serialize_activity(activity), to=room_name(session.id))
            return {"ok": True, "session": state}
        except (ValidationError, ValueError, LiveValidationError) as exc:
            db.session.rollback()
            return {"ok": False, "error": validation_message(exc)}

    @socketio.on("live:moderate_response")
    def socket_moderate_response(data):
        if not current_user.is_authenticated or not getattr(current_user, "puede_acceder_live", False):
            return {"ok": False, "error": "No tienes acceso a Live."}
        if current_user.rol != "administrador":
            return {"ok": False, "error": "Solo administradores pueden moderar."}

        session = resolve_session(data or {})
        if session is None:
            return {"ok": False, "error": "Sesion no encontrada."}
        activity = db.session.get(LiveActivity, int((data or {}).get("activity_id") or 0))
        if activity is None or activity.session_id != session.id:
            return {"ok": False, "error": "Actividad no encontrada."}
        try:
            response = moderate_response(
                session,
                activity,
                int((data or {}).get("response_id") or 0),
                str((data or {}).get("action") or "approve"),
            )
            db.session.commit()
            payload = {"session_id": session.id, "activity_id": activity.id, "results": aggregate_results(activity)}
            emit("live:results_updated", payload, to=room_name(session.id))
            emit("live:activity_state", serialize_activity(activity), to=room_name(session.id))
            return {"ok": True, "response_id": response.id, "results": payload["results"]}
        except (ValidationError, ValueError, LiveValidationError) as exc:
            db.session.rollback()
            return {"ok": False, "error": validation_message(exc)}


def resolve_session(data: dict) -> LiveSession | None:
    session_id = data.get("session_id")
    if session_id:
        return db.session.get(LiveSession, int(session_id))
    return find_session_by_code(data.get("code"))


def participant_count_payload(session: LiveSession) -> dict:
    return {
        "session_id": session.id,
        "participant_count": len(session.participants),
        "connected_count": len([participant for participant in session.participants if participant.connected]),
    }


def validation_message(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        return str(first.get("msg") or "Datos inválidos.")
    return str(exc)
