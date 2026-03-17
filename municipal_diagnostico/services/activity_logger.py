from __future__ import annotations

import secrets

from flask import request, session
from flask_login import current_user

from municipal_diagnostico.extensions import db
from municipal_diagnostico.models import ActividadPlataforma, SesionPlataforma
from municipal_diagnostico.timeutils import to_localtime, utcnow


SESSION_KEY_NAME = "platform_session_key"


def _current_session_key() -> str | None:
    return session.get(SESSION_KEY_NAME)


def _request_ip() -> str | None:
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.remote_addr


def current_platform_session() -> SesionPlataforma | None:
    if not current_user.is_authenticated:
        return None
    session_key = _current_session_key()
    if not session_key:
        return None
    return SesionPlataforma.query.filter_by(
        session_key=session_key,
        usuario_id=current_user.id,
    ).first()


def open_platform_session(user) -> SesionPlataforma:
    existing = current_platform_session()
    if existing and existing.activa:
        existing.ultima_actividad_at = utcnow()
        return existing

    session_key = secrets.token_urlsafe(24)
    record = SesionPlataforma(
        usuario=user,
        session_key=session_key,
        ip=_request_ip(),
        user_agent=(request.user_agent.string or "")[:512] or None,
        iniciada_at=utcnow(),
        ultima_actividad_at=utcnow(),
        activa=True,
    )
    db.session.add(record)
    session[SESSION_KEY_NAME] = session_key
    return record


def touch_platform_session(commit: bool = False) -> SesionPlataforma | None:
    record = current_platform_session()
    if record is None:
        return None
    record.ultima_actividad_at = utcnow()
    if commit:
        db.session.commit()
    return record


def close_platform_session() -> None:
    record = current_platform_session()
    if record is None:
        session.pop(SESSION_KEY_NAME, None)
        return
    record.ultima_actividad_at = utcnow()
    record.cerrada_at = utcnow()
    record.activa = False
    session.pop(SESSION_KEY_NAME, None)


def log_activity(
    activity_type: str,
    *,
    entity_type: str | None = None,
    entity_id: int | None = None,
    metadata: dict | None = None,
    commit: bool = True,
) -> ActividadPlataforma:
    record = touch_platform_session(commit=False)
    activity = ActividadPlataforma(
        sesion=record,
        usuario_id=current_user.id if current_user.is_authenticated else None,
        tipo=activity_type,
        ruta=request.path if request else None,
        metodo=request.method if request else None,
        entidad_tipo=entity_type,
        entidad_id=entity_id,
        metadata_json=metadata or None,
    )
    db.session.add(activity)
    if commit:
        db.session.commit()
    return activity


def local_session_timestamp(record: SesionPlataforma | None):
    if record is None:
        return None
    return to_localtime(record.ultima_actividad_at)
