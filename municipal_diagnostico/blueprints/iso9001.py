from __future__ import annotations

from datetime import date
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    url_for,
)
from flask_login import current_user

from municipal_diagnostico.decorators import iso9001_role_required
from municipal_diagnostico.extensions import db
from municipal_diagnostico.models import (
    Dependencia,
    Iso9001Asignacion,
    Iso9001Ciclo,
    Iso9001Evaluacion,
    Iso9001Evidencia,
    Iso9001Respuesta,
    Iso9001ObservacionRevision,
    Usuario,
)
from municipal_diagnostico.services.activity_logger import log_activity
from municipal_diagnostico.services.iso9001 import (
    ISO9001_CYCLE_STATES,
    ISO9001_EVALUATION_STATES,
    ISO9001_FINAL_STATES,
    ISO9001_OPTION_LABELS,
    ISO9001_OPTION_POINTS,
    ensure_iso9001_catalog,
    list_visible_iso9001_evaluations,
    summarize_iso9001_cycle,
    summarize_iso9001_evaluation,
)
from municipal_diagnostico.services.iso9001_exports import build_iso9001_excel, build_iso9001_pdf
from municipal_diagnostico.timeutils import utcnow
from municipal_diagnostico.utils import allowed_file, store_upload


bp = Blueprint("iso9001", __name__, url_prefix="/iso9001")


@bp.route("/")
@iso9001_role_required("administrador", "revisor", "evaluador", "respondente", "consulta")
def dashboard():
    ensure_iso9001_catalog()
    evaluations = list_visible_iso9001_evaluations(current_user)
    cycles = Iso9001Ciclo.query.order_by(Iso9001Ciclo.created_at.desc()).all()
    summaries = [{"evaluacion": evaluation, "summary": summarize_iso9001_evaluation(evaluation)} for evaluation in evaluations[:8]]
    log_activity("view_iso9001_dashboard", metadata={"modulo": "iso9001", "rol": current_user.rol})
    return render_template(
        "iso9001/dashboard.html",
        cycles=cycles,
        evaluations=evaluations,
        summaries=summaries,
        counts={
            "ciclos": len(cycles),
            "evaluaciones": len(evaluations),
            "en_revision": sum(1 for item in evaluations if item.estado == "en_revision"),
            "cerradas": sum(1 for item in evaluations if item.estado in ISO9001_FINAL_STATES),
        },
    )


@bp.route("/ciclos", methods=["GET", "POST"])
@iso9001_role_required("administrador")
def cycles():
    version = ensure_iso9001_catalog()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "create_cycle":
            data, error = validate_cycle_payload(request.form)
            if error:
                flash(error, "error")
            else:
                cycle = Iso9001Ciclo(
                    nombre=data["nombre"],
                    descripcion=data["descripcion"],
                    estado=data["estado"],
                    fecha_inicio=data["fecha_inicio"],
                    fecha_cierre=data["fecha_cierre"],
                    version=version,
                    creado_por=current_user,
                )
                db.session.add(cycle)
                db.session.commit()
                log_activity("create_iso9001_cycle", entity_type="iso9001_ciclo", entity_id=cycle.id)
                flash("Ciclo ISO registrado.", "success")

        elif action == "change_cycle_state":
            cycle = Iso9001Ciclo.query.get_or_404(request.form.get("cycle_id", type=int))
            next_state = clean_text(request.form.get("estado"))
            if next_state not in ISO9001_CYCLE_STATES:
                flash("Selecciona un estado valido para el ciclo.", "error")
            else:
                cycle.estado = next_state
                db.session.commit()
                log_activity("change_iso9001_cycle_state", entity_type="iso9001_ciclo", entity_id=cycle.id, metadata={"estado": next_state})
                flash("Estado del ciclo actualizado.", "success")

        elif action == "add_evaluations":
            cycle = Iso9001Ciclo.query.get_or_404(request.form.get("cycle_id", type=int))
            created = create_evaluations_from_form(cycle)
            db.session.commit()
            log_activity("create_iso9001_evaluations", entity_type="iso9001_ciclo", entity_id=cycle.id, metadata={"created": created})
            flash(f"Evaluaciones registradas: {created}.", "success" if created else "error")

        elif action == "update_evaluation":
            evaluation = Iso9001Evaluacion.query.get_or_404(request.form.get("evaluation_id", type=int))
            sync_evaluation_assignment(evaluation)
            next_state = clean_text(request.form.get("estado")) or evaluation.estado
            if next_state not in ISO9001_EVALUATION_STATES:
                flash("Selecciona un estado valido para la evaluacion.", "error")
            else:
                evaluation.estado = next_state
                if next_state == "cerrada" and evaluation.cerrada_at is None:
                    evaluation.cerrada_at = utcnow()
                db.session.commit()
                log_activity("update_iso9001_evaluation", entity_type="iso9001_evaluacion", entity_id=evaluation.id)
                flash("Evaluacion ISO actualizada.", "success")

        return redirect(url_for("iso9001.cycles"))

    cycles_list = Iso9001Ciclo.query.order_by(Iso9001Ciclo.created_at.desc()).all()
    selected_cycle_id = request.args.get("cycle_id", type=int)
    selected_cycle = select_cycle(cycles_list, selected_cycle_id)
    selected_summary = summarize_iso9001_cycle(selected_cycle) if selected_cycle else None
    capture_users = Usuario.query.filter(Usuario.activo.is_(True)).order_by(Usuario.nombre).all()
    reviewers = Usuario.query.filter(
        Usuario.activo.is_(True),
        Usuario.rol.in_(["administrador", "revisor"]),
    ).order_by(Usuario.nombre).all()
    dependencies = Dependencia.query.filter_by(activa=True).order_by(Dependencia.nombre).all()
    log_activity("view_iso9001_cycles")
    return render_template(
        "iso9001/cycles.html",
        cycles=cycles_list,
        selected_cycle=selected_cycle,
        selected_summary=selected_summary,
        users=capture_users,
        reviewers=reviewers,
        dependencies=dependencies,
        cycle_states=ISO9001_CYCLE_STATES,
        evaluation_states=ISO9001_EVALUATION_STATES,
    )


@bp.route("/evaluaciones/<int:evaluation_id>", methods=["GET", "POST"])
@iso9001_role_required("administrador", "revisor", "evaluador", "respondente", "consulta")
def evaluation_detail(evaluation_id: int):
    evaluation = Iso9001Evaluacion.query.get_or_404(evaluation_id)
    if not user_can_view_evaluation(evaluation):
        abort(403)

    if request.method == "POST":
        if not user_can_edit_evaluation(evaluation):
            flash("La evaluacion ISO no esta disponible para edicion.", "error")
            return redirect(url_for("iso9001.evaluation_detail", evaluation_id=evaluation.id))
        section_id = request.form.get("apartado_id", type=int)
        if section_id is None:
            abort(400)
        section = get_section_or_404(evaluation, section_id)
        saved, files = persist_section_from_form(evaluation, section)
        if evaluation.estado in {"borrador", "devuelta"}:
            evaluation.estado = "en_captura"
        summary = summarize_iso9001_evaluation(evaluation)
        db.session.commit()
        log_activity(
            "save_iso9001_section",
            entity_type="iso9001_evaluacion",
            entity_id=evaluation.id,
            metadata={"apartado_id": section.id, "responses": saved, "files": files},
        )
        flash(f"Apartado guardado. Respuestas: {saved} | Evidencias: {files}.", "success")
        return redirect(url_for("iso9001.evaluation_detail", evaluation_id=evaluation.id, _anchor=f"apartado-{section.id}"))

    summary = summarize_iso9001_evaluation(evaluation)
    can_edit = user_can_edit_evaluation(evaluation)
    log_activity("view_iso9001_evaluation", entity_type="iso9001_evaluacion", entity_id=evaluation.id)
    return render_template(
        "iso9001/evaluation_detail.html",
        evaluation=evaluation,
        summary=summary,
        option_labels=ISO9001_OPTION_LABELS,
        can_edit=can_edit,
    )


@bp.route("/evaluaciones/<int:evaluation_id>/enviar", methods=["POST"])
@iso9001_role_required("administrador", "revisor", "evaluador", "respondente", "consulta")
def submit_evaluation(evaluation_id: int):
    evaluation = Iso9001Evaluacion.query.get_or_404(evaluation_id)
    if not user_can_edit_evaluation(evaluation):
        abort(403)
    summary = summarize_iso9001_evaluation(evaluation)
    if summary["completion"] < 100:
        flash("Debes responder todos los reactivos antes de enviar a revision.", "error")
        return redirect(url_for("iso9001.evaluation_detail", evaluation_id=evaluation.id))
    evaluation.estado = "en_revision"
    evaluation.enviada_revision_at = utcnow()
    db.session.commit()
    log_activity("submit_iso9001_review", entity_type="iso9001_evaluacion", entity_id=evaluation.id)
    flash("Evaluacion enviada a revision.", "success")
    return redirect(url_for("iso9001.dashboard"))


@bp.route("/evaluaciones/<int:evaluation_id>/revision", methods=["GET", "POST"])
@iso9001_role_required("administrador", "revisor")
def review_evaluation(evaluation_id: int):
    evaluation = Iso9001Evaluacion.query.get_or_404(evaluation_id)
    if not user_can_review_evaluation(evaluation):
        abort(403)

    if request.method == "POST":
        action = request.form.get("action")
        comentario = clean_text(request.form.get("comentario"))
        summary = summarize_iso9001_evaluation(evaluation)
        if action not in {"return", "close"}:
            flash("Selecciona una accion de revision valida.", "error")
        elif not comentario:
            flash("Captura una observacion de revision.", "error")
        elif evaluation.estado != "en_revision":
            flash("Solo puedes revisar evaluaciones enviadas formalmente a revision.", "error")
        elif action == "close" and summary["completion"] < 100:
            flash("El cierre oficial requiere 100% de reactivos respondidos.", "error")
        else:
            evaluation.estado = "devuelta" if action == "return" else "cerrada"
            if action == "close":
                evaluation.cerrada_at = utcnow()
            db.session.add(
                Iso9001ObservacionRevision(
                    evaluacion=evaluation,
                    autor=current_user,
                    accion=action,
                    comentario=comentario,
                )
            )
            db.session.commit()
            log_activity("review_iso9001_evaluation", entity_type="iso9001_evaluacion", entity_id=evaluation.id, metadata={"accion": action})
            flash("Evaluacion devuelta." if action == "return" else "Evaluacion cerrada como resultado oficial.", "success")
            return redirect(url_for("iso9001.review_evaluation", evaluation_id=evaluation.id))

    summary = summarize_iso9001_evaluation(evaluation)
    log_activity("view_iso9001_review", entity_type="iso9001_evaluacion", entity_id=evaluation.id)
    return render_template("iso9001/review.html", evaluation=evaluation, summary=summary)


@bp.route("/reportes")
@iso9001_role_required("administrador", "revisor", "evaluador", "respondente", "consulta")
def reports():
    cycles_list = Iso9001Ciclo.query.order_by(Iso9001Ciclo.created_at.desc()).all()
    selected_cycle = select_cycle(cycles_list, request.args.get("cycle_id", type=int))
    selected_summary = summarize_iso9001_cycle(selected_cycle, role=current_user.rol, user=current_user) if selected_cycle else None
    log_activity("view_iso9001_reports")
    return render_template(
        "iso9001/reports.html",
        cycles=cycles_list,
        selected_cycle=selected_cycle,
        selected_summary=selected_summary,
    )


@bp.route("/reportes/<int:evaluation_id>/pdf")
@iso9001_role_required("administrador", "revisor", "evaluador", "respondente", "consulta")
def report_pdf(evaluation_id: int):
    evaluation = Iso9001Evaluacion.query.get_or_404(evaluation_id)
    if not user_can_view_evaluation(evaluation):
        abort(403)
    buffer = build_iso9001_pdf(evaluation)
    log_activity("export_iso9001_pdf", entity_type="iso9001_evaluacion", entity_id=evaluation.id)
    return send_file(buffer, mimetype="application/pdf", as_attachment=True, download_name=f"iso9001-{evaluation.id}.pdf")


@bp.route("/reportes/<int:evaluation_id>/xlsx")
@iso9001_role_required("administrador", "revisor", "evaluador", "respondente", "consulta")
def report_excel(evaluation_id: int):
    evaluation = Iso9001Evaluacion.query.get_or_404(evaluation_id)
    if not user_can_view_evaluation(evaluation):
        abort(403)
    buffer = build_iso9001_excel(evaluation)
    log_activity("export_iso9001_xlsx", entity_type="iso9001_evaluacion", entity_id=evaluation.id)
    return send_file(
        buffer,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"iso9001-{evaluation.id}.xlsx",
    )


@bp.route("/evidencias/<int:evidence_id>/descargar")
@iso9001_role_required("administrador", "revisor", "evaluador", "respondente", "consulta")
def download_evidence(evidence_id: int):
    evidence = Iso9001Evidencia.query.get_or_404(evidence_id)
    evaluation = evidence.respuesta.evaluacion
    if not user_can_view_evaluation(evaluation):
        abort(403)
    path = Path(evidence.archivo_guardado)
    root = Path(current_app.config["UPLOAD_FOLDER"]) / path.parent
    log_activity("download_iso9001_evidence", entity_type="iso9001_evidencia", entity_id=evidence.id)
    return send_from_directory(root, path.name, as_attachment=True, download_name=evidence.archivo_nombre_original)


def validate_cycle_payload(form_data):
    nombre = clean_text(form_data.get("nombre"))
    descripcion = clean_text(form_data.get("descripcion"))
    estado = clean_text(form_data.get("estado")) or "activo"
    if not nombre:
        return None, "Captura el nombre del ciclo ISO."
    if estado not in ISO9001_CYCLE_STATES:
        return None, "Selecciona un estado valido."
    if Iso9001Ciclo.query.filter_by(nombre=nombre).first():
        return None, "Ya existe un ciclo ISO con ese nombre."
    try:
        fecha_inicio = date.fromisoformat(form_data.get("fecha_inicio"))
        fecha_cierre = date.fromisoformat(form_data.get("fecha_cierre"))
    except Exception:
        return None, "Captura fechas validas para el ciclo."
    if fecha_cierre < fecha_inicio:
        return None, "La fecha de cierre no puede ser anterior al inicio."
    return {
        "nombre": nombre,
        "descripcion": descripcion,
        "estado": estado,
        "fecha_inicio": fecha_inicio,
        "fecha_cierre": fecha_cierre,
    }, None


def create_evaluations_from_form(cycle: Iso9001Ciclo) -> int:
    created = 0
    responsable_id = request.form.get("responsable_id", type=int)
    revisor_id = request.form.get("revisor_id", type=int)
    dependency_ids = [int(value) for value in request.form.getlist("dependencia_ids") if value]
    responsable = active_user_or_none(responsable_id)
    revisor = active_user_or_none(revisor_id)
    for dependency_id in dependency_ids:
        dependency = db.session.get(Dependencia, dependency_id)
        if dependency is None:
            continue
        existing = Iso9001Evaluacion.query.filter_by(ciclo_id=cycle.id, dependencia_id=dependency.id).first()
        if existing:
            continue
        evaluation = Iso9001Evaluacion(
            ciclo=cycle,
            dependencia=dependency,
            revisor=revisor,
            estado="borrador",
        )
        db.session.add(evaluation)
        db.session.flush()
        if responsable:
            grant_iso_access(responsable)
            db.session.add(Iso9001Asignacion(evaluacion=evaluation, usuario=responsable, tipo="captura"))
        if revisor:
            grant_iso_access(revisor)
        created += 1
    return created


def sync_evaluation_assignment(evaluation: Iso9001Evaluacion) -> None:
    responsable_id = request.form.get("responsable_id", type=int)
    revisor_id = request.form.get("revisor_id", type=int)
    evaluation.revisor = active_user_or_none(revisor_id)
    if evaluation.revisor:
        grant_iso_access(evaluation.revisor)
    for assignment in list(evaluation.asignaciones):
        if assignment.tipo == "captura" and assignment.usuario_id != responsable_id:
            db.session.delete(assignment)
    if responsable_id and not any(assignment.usuario_id == responsable_id and assignment.tipo == "captura" for assignment in evaluation.asignaciones):
        user = active_user_or_none(responsable_id)
        if user:
            grant_iso_access(user)
            db.session.add(Iso9001Asignacion(evaluacion=evaluation, usuario=user, tipo="captura"))


def persist_section_from_form(evaluation: Iso9001Evaluacion, section) -> tuple[int, int]:
    response_map = {response.reactivo_id: response for response in evaluation.respuestas}
    saved = 0
    uploaded = 0
    for reactive in section.reactivos:
        selected = request.form.get(f"calificacion_{reactive.id}")
        if selected not in ISO9001_OPTION_POINTS:
            continue
        response = response_map.get(reactive.id)
        if response is None:
            response = Iso9001Respuesta(evaluacion=evaluation, reactivo=reactive, usuario=current_user, calificacion=selected)
            db.session.add(response)
            db.session.flush()
        response.calificacion = selected
        response.valor = ISO9001_OPTION_POINTS[selected]
        response.observacion = clean_text(request.form.get(f"observacion_{reactive.id}"))
        response.usuario = current_user
        saved += 1
        for upload in request.files.getlist(f"evidencias_{reactive.id}"):
            if not upload or not upload.filename:
                continue
            if not allowed_file(upload.filename):
                flash(f"Archivo rechazado en reactivo {reactive.numero}: formato no permitido.", "error")
                continue
            size = get_file_size(upload)
            stored = store_upload(upload, f"iso9001/evaluaciones/{evaluation.id}/reactivos/{reactive.id}")
            db.session.add(
                Iso9001Evidencia(
                    respuesta=response,
                    usuario=current_user,
                    archivo_nombre_original=upload.filename,
                    archivo_guardado=stored,
                    mime_type=upload.mimetype or "application/octet-stream",
                    tamano_bytes=size,
                    activo=True,
                )
            )
            uploaded += 1
    return saved, uploaded


def user_can_view_evaluation(evaluation: Iso9001Evaluacion) -> bool:
    if current_user.rol == "administrador":
        return True
    if any(assignment.usuario_id == current_user.id and assignment.tipo == "captura" for assignment in evaluation.asignaciones):
        return True
    if current_user.rol == "revisor":
        return evaluation.revisor_id == current_user.id or evaluation.estado in ISO9001_FINAL_STATES
    if current_user.rol == "consulta":
        return evaluation.estado in ISO9001_FINAL_STATES
    return any(assignment.usuario_id == current_user.id for assignment in evaluation.asignaciones)


def user_can_edit_evaluation(evaluation: Iso9001Evaluacion) -> bool:
    if not evaluation.editable:
        return False
    if current_user.rol == "administrador":
        return True
    return any(assignment.usuario_id == current_user.id and assignment.tipo == "captura" for assignment in evaluation.asignaciones)


def user_can_review_evaluation(evaluation: Iso9001Evaluacion) -> bool:
    return current_user.rol == "administrador" or evaluation.revisor_id == current_user.id


def get_section_or_404(evaluation: Iso9001Evaluacion, section_id: int):
    for clause in evaluation.ciclo.version.clausulas:
        for section in clause.apartados:
            if section.id == section_id:
                return section
    abort(404)


def select_cycle(cycles: list[Iso9001Ciclo], selected_cycle_id: int | None):
    if not cycles:
        return None
    if selected_cycle_id:
        selected = next((cycle for cycle in cycles if cycle.id == selected_cycle_id), None)
        if selected:
            return selected
    active = next((cycle for cycle in cycles if cycle.estado == "activo"), None)
    return active or cycles[0]


def clean_text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def active_user_or_none(user_id: int | None) -> Usuario | None:
    if not user_id:
        return None
    user = db.session.get(Usuario, user_id)
    if user is None or not user.activo:
        return None
    return user


def grant_iso_access(user: Usuario) -> None:
    if not user.acceso_iso9001:
        user.acceso_iso9001 = True


def get_file_size(file_storage) -> int:
    stream = file_storage.stream
    position = stream.tell()
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(position)
    return size
