from __future__ import annotations

from datetime import date
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    url_for,
)
from flask_login import current_user

from municipal_diagnostico.decorators import iso45001_role_required
from municipal_diagnostico.extensions import db
from municipal_diagnostico.iso45001_seed_data import ISO45001_VERSION
from municipal_diagnostico.models import (
    Dependencia,
    Iso45001Asignacion,
    Iso45001Ciclo,
    Iso45001EvidenciaDocumental,
    Iso45001Evaluacion,
    Iso45001Evidencia,
    Iso45001ObservacionRevision,
    Iso45001Respuesta,
    Usuario,
)
from municipal_diagnostico.services.activity_logger import log_activity
from municipal_diagnostico.services.iso45001 import (
    ISO45001_CYCLE_STATES,
    ISO45001_EVALUATION_STATES,
    ISO45001_FINAL_STATES,
    ISO45001_OPTION_LABELS,
    ISO45001_OPTION_POINTS,
    ensure_document_controls_for_evaluation,
    ensure_iso45001_catalog,
    format_iso_datetime,
    list_visible_iso45001_evaluations,
    list_document_evidences,
    save_document_control_payload,
    summarize_iso45001_cycle,
    summarize_iso45001_evaluation,
    upload_document_evidence,
    validate_iso45001_submission,
)
from municipal_diagnostico.services.iso45001_exports import build_iso45001_excel, build_iso45001_pdf
from municipal_diagnostico.timeutils import utcnow
from municipal_diagnostico.utils import allowed_file, store_upload


bp = Blueprint("iso45001", __name__, url_prefix="/iso45001")


@bp.route("/")
@iso45001_role_required("administrador", "revisor", "evaluador", "respondente", "consulta")
def dashboard():
    ensure_iso45001_catalog()
    evaluations = list_visible_iso45001_evaluations(current_user)
    cycles = Iso45001Ciclo.query.order_by(Iso45001Ciclo.created_at.desc()).all()
    summaries = [{"evaluacion": evaluation, "summary": summarize_iso45001_evaluation(evaluation)} for evaluation in evaluations[:8]]
    log_activity("view_iso45001_dashboard", metadata={"modulo": "iso45001", "rol": current_user.rol})
    return render_template(
        "iso45001/dashboard.html",
        cycles=cycles,
        evaluations=evaluations,
        summaries=summaries,
        diagnostic_notice=_diagnostic_notice(),
        counts={
            "ciclos": len(cycles),
            "evaluaciones": len(evaluations),
            "en_revision": sum(1 for item in evaluations if item.estado == "en_revision"),
            "cerradas": sum(1 for item in evaluations if item.estado in ISO45001_FINAL_STATES),
        },
    )


@bp.route("/ciclos", methods=["GET", "POST"])
@iso45001_role_required("administrador")
def cycles():
    version = ensure_iso45001_catalog()
    if request.method == "POST":
        action = request.form.get("action")
        redirect_url = url_for("iso45001.cycles")
        if action == "create_cycle":
            data, error = validate_cycle_payload(request.form)
            if error:
                flash(error, "error")
            else:
                cycle = Iso45001Ciclo(
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
                log_activity("create_iso45001_cycle", entity_type="iso45001_ciclo", entity_id=cycle.id)
                flash("Ciclo ISO 45001 registrado.", "success")
                redirect_url = url_for("iso45001.cycles", cycle_id=cycle.id)

        elif action == "change_cycle_state":
            cycle = Iso45001Ciclo.query.get_or_404(request.form.get("cycle_id", type=int))
            redirect_url = url_for("iso45001.cycles", cycle_id=cycle.id)
            next_state = clean_text(request.form.get("estado"))
            if next_state not in ISO45001_CYCLE_STATES:
                flash("Selecciona un estado válido para el ciclo.", "error")
            else:
                cycle.estado = next_state
                db.session.commit()
                log_activity(
                    "change_iso45001_cycle_state",
                    entity_type="iso45001_ciclo",
                    entity_id=cycle.id,
                    metadata={"estado": next_state},
                )
                flash("Estado del ciclo actualizado.", "success")

        elif action == "delete_cycle":
            cycle = Iso45001Ciclo.query.get_or_404(request.form.get("cycle_id", type=int))
            if iso45001_cycle_has_activity(cycle):
                redirect_url = url_for("iso45001.cycles", cycle_id=cycle.id)
                flash("No se puede eliminar un ciclo con respuestas u observaciones registradas.", "error")
            else:
                cycle_id = cycle.id
                db.session.delete(cycle)
                db.session.commit()
                log_activity("delete_iso45001_cycle", entity_type="iso45001_ciclo", entity_id=cycle_id)
                flash("Ciclo ISO 45001 eliminado.", "success")

        elif action == "add_evaluations":
            cycle = Iso45001Ciclo.query.get_or_404(request.form.get("cycle_id", type=int))
            redirect_url = url_for("iso45001.cycles", cycle_id=cycle.id)
            created = create_evaluations_from_form(cycle)
            db.session.commit()
            log_activity(
                "create_iso45001_evaluations",
                entity_type="iso45001_ciclo",
                entity_id=cycle.id,
                metadata={"created": created},
            )
            flash(f"Evaluaciones registradas: {created}.", "success" if created else "error")

        elif action == "update_evaluation":
            evaluation = Iso45001Evaluacion.query.get_or_404(request.form.get("evaluation_id", type=int))
            redirect_url = url_for("iso45001.cycles", cycle_id=evaluation.ciclo_id)
            data, error = validate_evaluation_update_payload(request.form, evaluation)
            if error:
                flash(error, "error")
            elif data["estado"] in {"en_revision", "cerrada"}:
                validation = validate_iso45001_submission(evaluation)
                if not validation["ok"]:
                    flash(_submission_blocker_message(validation), "error")
                else:
                    _apply_evaluation_update(evaluation, data)
                    db.session.commit()
                    log_activity("update_iso45001_evaluation", entity_type="iso45001_evaluacion", entity_id=evaluation.id)
                    flash("Evaluación ISO 45001 actualizada.", "success")
            else:
                _apply_evaluation_update(evaluation, data)
                db.session.commit()
                log_activity("update_iso45001_evaluation", entity_type="iso45001_evaluacion", entity_id=evaluation.id)
                flash("Evaluación ISO 45001 actualizada.", "success")

        elif action == "delete_evaluation":
            evaluation = Iso45001Evaluacion.query.get_or_404(request.form.get("evaluation_id", type=int))
            redirect_url = url_for("iso45001.cycles", cycle_id=evaluation.ciclo_id)
            if iso45001_evaluation_has_activity(evaluation):
                flash("No se puede desasignar una dependencia con respuestas u observaciones registradas.", "error")
            else:
                evaluation_id = evaluation.id
                cycle_id = evaluation.ciclo_id
                dependency_id = evaluation.dependencia_id
                db.session.delete(evaluation)
                db.session.commit()
                log_activity(
                    "delete_iso45001_evaluation",
                    entity_type="iso45001_evaluacion",
                    entity_id=evaluation_id,
                    metadata={"ciclo_id": cycle_id, "dependencia_id": dependency_id},
                )
                flash("Dependencia desasignada del ciclo.", "success")

        return redirect(redirect_url)

    cycles_list = Iso45001Ciclo.query.order_by(Iso45001Ciclo.created_at.desc()).all()
    selected_cycle = select_cycle(cycles_list, request.args.get("cycle_id", type=int))
    selected_summary = summarize_iso45001_cycle(selected_cycle) if selected_cycle else None
    capture_users = Usuario.query.filter(Usuario.activo.is_(True)).order_by(Usuario.nombre).all()
    reviewers = (
        Usuario.query.filter(
            Usuario.activo.is_(True),
            Usuario.rol.in_(["administrador", "revisor"]),
        )
        .order_by(Usuario.nombre)
        .all()
    )
    dependencies = Dependencia.query.filter_by(activa=True).order_by(Dependencia.nombre).all()
    log_activity("view_iso45001_cycles")
    return render_template(
        "iso45001/cycles.html",
        cycles=cycles_list,
        selected_cycle=selected_cycle,
        selected_summary=selected_summary,
        users=capture_users,
        reviewers=reviewers,
        dependencies=dependencies,
        cycle_states=ISO45001_CYCLE_STATES,
        evaluation_states=ISO45001_EVALUATION_STATES,
        diagnostic_notice=_diagnostic_notice(),
    )


@bp.route("/evaluaciones/<int:evaluation_id>", methods=["GET", "POST"])
@iso45001_role_required("administrador", "revisor", "evaluador", "respondente", "consulta")
def evaluation_detail(evaluation_id: int):
    evaluation = Iso45001Evaluacion.query.get_or_404(evaluation_id)
    if not user_can_view_evaluation(evaluation):
        abort(403)

    if request.method == "POST":
        if not user_can_edit_evaluation(evaluation):
            flash("La evaluación ISO 45001 no está disponible para edición.", "error")
            return redirect(url_for("iso45001.evaluation_detail", evaluation_id=evaluation.id))
        section_id = request.form.get("apartado_id", type=int)
        if section_id is None:
            abort(400)
        section = get_section_or_404(evaluation, section_id)
        invalid_options = invalid_section_form_options(section)
        if invalid_options:
            flash("Solo se permiten las respuestas No, Parcial y Sí; N/A no está disponible.", "error")
            return redirect(url_for("iso45001.evaluation_detail", evaluation_id=evaluation.id, _anchor=f"apartado-{section.id}"))
        saved, files = persist_section_from_form(evaluation, section)
        if evaluation.estado in {"borrador", "devuelta"}:
            evaluation.estado = "en_captura"
        summarize_iso45001_evaluation(evaluation)
        db.session.commit()
        log_activity(
            "save_iso45001_section",
            entity_type="iso45001_evaluacion",
            entity_id=evaluation.id,
            metadata={"apartado_id": section.id, "responses": saved, "files": files},
        )
        flash(f"Apartado guardado. Respuestas: {saved} | Evidencias: {files}.", "success")
        return redirect(url_for("iso45001.evaluation_detail", evaluation_id=evaluation.id, _anchor=f"apartado-{section.id}"))

    summary = summarize_iso45001_evaluation(evaluation)
    document_controls_summary = _normalize_document_controls(summary.get("document_controls") or [])
    can_edit = user_can_edit_evaluation(evaluation)
    log_activity("view_iso45001_evaluation", entity_type="iso45001_evaluacion", entity_id=evaluation.id)
    return render_template(
        "iso45001/evaluation_detail.html",
        evaluation=evaluation,
        summary=summary,
        document_overview=_document_control_overview(document_controls_summary),
        has_document_controls=bool(document_controls_summary),
        option_labels=ISO45001_OPTION_LABELS,
        can_edit=can_edit,
        diagnostic_notice=_diagnostic_notice(),
    )


@bp.route("/evaluaciones/<int:evaluation_id>/documentacion")
@iso45001_role_required("administrador", "revisor", "evaluador", "respondente", "consulta")
def document_controls(evaluation_id: int):
    """Show the shared evidence library and coverage controls for one evaluation.

    A document is evaluated once at control level and can support many
    reactives.  This deliberately lives outside the reactive-capture route so
    a file is never duplicated merely because it maps to more than one point.
    """

    evaluation = Iso45001Evaluacion.query.get_or_404(evaluation_id)
    if not user_can_view_evaluation(evaluation):
        abort(403)

    summary = summarize_iso45001_evaluation(evaluation)
    controls = _normalize_document_controls(summary.get("document_controls") or [])
    if not controls:
        flash(
            "Esta evaluación usa un catálogo anterior sin controles documentales compartidos. "
            "Sus evidencias por reactivo se conservan sólo para consulta.",
            "warning",
        )
        return redirect(url_for("iso45001.evaluation_detail", evaluation_id=evaluation.id))

    evidence_library = list_document_evidences(evaluation)
    log_activity(
        "view_iso45001_document_controls",
        entity_type="iso45001_evaluacion",
        entity_id=evaluation.id,
    )
    return render_template(
        "iso45001/document_controls.html",
        evaluation=evaluation,
        summary=summary,
        document_controls=controls,
        document_groups=_group_document_controls(controls),
        document_overview=_document_control_overview(controls),
        document_evidences=evidence_library,
        can_edit=user_can_edit_evaluation(evaluation),
        diagnostic_notice=_diagnostic_notice(),
    )


@bp.route("/evaluaciones/<int:evaluation_id>/documentacion/controles/<int:control_id>", methods=["POST"])
@iso45001_role_required("administrador", "revisor", "evaluador", "respondente", "consulta")
def save_document_control(evaluation_id: int, control_id: int):
    """Persist points, observation and reused document links for one control."""

    evaluation = Iso45001Evaluacion.query.get_or_404(evaluation_id)
    if not user_can_edit_evaluation(evaluation):
        abort(403)

    payload = {
        "punto_ids": request.form.getlist("punto_ids", type=int),
        "evidencia_ids": request.form.getlist("evidencia_ids", type=int),
        "observacion": clean_text(request.form.get("observacion")) or "",
    }
    result = save_document_control_payload(evaluation, control_id, payload, user=current_user)
    if not result.get("ok", False):
        flash(result.get("error") or "No se pudo guardar el control documental.", "error")
        return redirect(
            url_for("iso45001.document_controls", evaluation_id=evaluation.id, _anchor=f"control-{control_id}")
        )

    if evaluation.estado in {"borrador", "devuelta"}:
        evaluation.estado = "en_captura"
    summarize_iso45001_evaluation(evaluation)
    db.session.commit()
    log_activity(
        "save_iso45001_document_control",
        entity_type="iso45001_evaluacion",
        entity_id=evaluation.id,
        metadata={
            "control_id": control_id,
            "points": len(payload["punto_ids"]),
            "evidences": len(payload["evidencia_ids"]),
        },
    )
    flash("Control documental guardado.", "success")
    return redirect(url_for("iso45001.document_controls", evaluation_id=evaluation.id, _anchor=f"control-{control_id}"))


@bp.route("/evaluaciones/<int:evaluation_id>/documentacion/evidencias", methods=["POST"])
@iso45001_role_required("administrador", "revisor", "evaluador", "respondente", "consulta")
def upload_document_control_evidence(evaluation_id: int):
    """Upload a file once into the evaluation library and optionally link it."""

    evaluation = Iso45001Evaluacion.query.get_or_404(evaluation_id)
    if not user_can_edit_evaluation(evaluation):
        abort(403)

    uploads = [item for item in request.files.getlist("archivos") if item and item.filename]
    control_ids = request.form.getlist("control_ids", type=int)
    if not uploads:
        flash("Selecciona al menos un archivo para agregar a la biblioteca documental.", "error")
        return redirect(url_for("iso45001.document_controls", evaluation_id=evaluation.id, _anchor="biblioteca-documental"))

    result = upload_document_evidence(evaluation, uploads, control_ids, user=current_user)
    if not result.get("ok", False):
        flash(result.get("error") or "No se pudo cargar la evidencia documental.", "error")
        return redirect(url_for("iso45001.document_controls", evaluation_id=evaluation.id, _anchor="biblioteca-documental"))

    if evaluation.estado in {"borrador", "devuelta"}:
        evaluation.estado = "en_captura"
    summarize_iso45001_evaluation(evaluation)
    db.session.commit()
    count = int(result.get("count") or len(uploads))
    log_activity(
        "upload_iso45001_document_evidence",
        entity_type="iso45001_evaluacion",
        entity_id=evaluation.id,
        metadata={"files": count, "control_ids": control_ids},
    )
    flash(f"{count} archivo(s) agregado(s) a la biblioteca documental.", "success")
    return redirect(url_for("iso45001.document_controls", evaluation_id=evaluation.id, _anchor="biblioteca-documental"))


@bp.route("/evaluaciones/<int:evaluation_id>/apartados/<int:section_id>/autosave", methods=["POST"])
@iso45001_role_required("administrador", "revisor", "evaluador", "respondente", "consulta")
def autosave_section(evaluation_id: int, section_id: int):
    evaluation = Iso45001Evaluacion.query.get_or_404(evaluation_id)
    if not user_can_edit_evaluation(evaluation):
        abort(403)

    section = get_section_or_404(evaluation, section_id)
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "El formato de autoguardado no es válido."}), 400
    if invalid_section_payload_options(section, payload):
        return jsonify({"ok": False, "error": "Solo se permiten las respuestas No, Parcial y Sí."}), 400

    saved = persist_section_from_payload(evaluation, section, payload)
    if evaluation.estado in {"borrador", "devuelta"}:
        evaluation.estado = "en_captura"
    summary = summarize_iso45001_evaluation(evaluation)
    db.session.commit()

    section_summary = next((item for item in summary["sections"] if item["id"] == section.id), None)
    last_saved_at = latest_section_timestamp(evaluation, section)
    log_activity(
        "autosave_iso45001_section",
        entity_type="iso45001_evaluacion",
        entity_id=evaluation.id,
        metadata={"apartado_id": section.id, "responses": saved},
    )
    return jsonify(
        {
            "ok": True,
            "completion": summary["completion"],
            "section_answered": section_summary["answered"] if section_summary else 0,
            "section_total": section_summary["total"] if section_summary else len(section.reactivos),
            "section_completion": section_summary["completion"] if section_summary else 0,
            "last_saved": format_iso_datetime(last_saved_at),
        }
    )


@bp.route("/evaluaciones/<int:evaluation_id>/enviar", methods=["POST"])
@iso45001_role_required("administrador", "revisor", "evaluador", "respondente", "consulta")
def submit_evaluation(evaluation_id: int):
    evaluation = Iso45001Evaluacion.query.get_or_404(evaluation_id)
    if not user_can_edit_evaluation(evaluation):
        abort(403)
    validation = validate_iso45001_submission(evaluation)
    if not validation["ok"]:
        flash(_submission_blocker_message(validation), "error")
        return redirect(url_for("iso45001.evaluation_detail", evaluation_id=evaluation.id))
    evaluation.estado = "en_revision"
    evaluation.enviada_revision_at = utcnow()
    db.session.commit()
    log_activity("submit_iso45001_review", entity_type="iso45001_evaluacion", entity_id=evaluation.id)
    flash("Evaluación ISO 45001 enviada a revisión.", "success")
    return redirect(url_for("iso45001.dashboard"))


@bp.route("/evaluaciones/<int:evaluation_id>/revision", methods=["GET", "POST"])
@iso45001_role_required("administrador", "revisor")
def review_evaluation(evaluation_id: int):
    evaluation = Iso45001Evaluacion.query.get_or_404(evaluation_id)
    if not user_can_review_evaluation(evaluation):
        abort(403)

    if request.method == "POST":
        action = request.form.get("action")
        comentario = clean_text(request.form.get("comentario"))
        validation = validate_iso45001_submission(evaluation)
        if action not in {"return", "close"}:
            flash("Selecciona una acción de revisión válida.", "error")
        elif not comentario:
            flash("Captura una observación de revisión.", "error")
        elif evaluation.estado != "en_revision":
            flash("Solo puedes revisar evaluaciones enviadas formalmente a revisión.", "error")
        elif action == "close" and not validation["ok"]:
            flash(_submission_blocker_message(validation), "error")
        else:
            evaluation.estado = "devuelta" if action == "return" else "cerrada"
            if action == "close":
                evaluation.cerrada_at = utcnow()
            db.session.add(
                Iso45001ObservacionRevision(
                    evaluacion=evaluation,
                    autor=current_user,
                    accion=action,
                    comentario=comentario,
                )
            )
            db.session.commit()
            log_activity(
                "review_iso45001_evaluation",
                entity_type="iso45001_evaluacion",
                entity_id=evaluation.id,
                metadata={"accion": action},
            )
            flash("Evaluación devuelta." if action == "return" else "Evaluación cerrada como resultado oficial.", "success")
            return redirect(url_for("iso45001.review_evaluation", evaluation_id=evaluation.id))

    summary = summarize_iso45001_evaluation(evaluation)
    log_activity("view_iso45001_review", entity_type="iso45001_evaluacion", entity_id=evaluation.id)
    return render_template(
        "iso45001/review.html",
        evaluation=evaluation,
        summary=summary,
        diagnostic_notice=_diagnostic_notice(),
    )


@bp.route("/reportes")
@iso45001_role_required("administrador", "revisor", "evaluador", "respondente", "consulta")
def reports():
    cycles_list = Iso45001Ciclo.query.order_by(Iso45001Ciclo.created_at.desc()).all()
    selected_cycle = select_cycle(cycles_list, request.args.get("cycle_id", type=int))
    selected_summary = summarize_iso45001_cycle(selected_cycle, role=current_user.rol, user=current_user) if selected_cycle else None
    log_activity("view_iso45001_reports")
    return render_template(
        "iso45001/reports.html",
        cycles=cycles_list,
        selected_cycle=selected_cycle,
        selected_summary=selected_summary,
        diagnostic_notice=_diagnostic_notice(),
    )


@bp.route("/reportes/<int:evaluation_id>/pdf")
@iso45001_role_required("administrador", "revisor", "evaluador", "respondente", "consulta")
def report_pdf(evaluation_id: int):
    evaluation = Iso45001Evaluacion.query.get_or_404(evaluation_id)
    if not user_can_view_evaluation(evaluation):
        abort(403)
    buffer = build_iso45001_pdf(evaluation)
    log_activity("export_iso45001_pdf", entity_type="iso45001_evaluacion", entity_id=evaluation.id)
    return send_file(buffer, mimetype="application/pdf", as_attachment=True, download_name=f"iso45001-{evaluation.id}.pdf")


@bp.route("/reportes/<int:evaluation_id>/xlsx")
@iso45001_role_required("administrador", "revisor", "evaluador", "respondente", "consulta")
def report_excel(evaluation_id: int):
    evaluation = Iso45001Evaluacion.query.get_or_404(evaluation_id)
    if not user_can_view_evaluation(evaluation):
        abort(403)
    buffer = build_iso45001_excel(evaluation)
    log_activity("export_iso45001_xlsx", entity_type="iso45001_evaluacion", entity_id=evaluation.id)
    return send_file(
        buffer,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"iso45001-{evaluation.id}.xlsx",
    )


@bp.route("/evidencias/<int:evidence_id>/descargar")
@iso45001_role_required("administrador", "revisor", "evaluador", "respondente", "consulta")
def download_evidence(evidence_id: int):
    evidence = Iso45001Evidencia.query.get_or_404(evidence_id)
    evaluation = evidence.respuesta.evaluacion
    if not user_can_view_evaluation(evaluation):
        abort(403)
    path = Path(evidence.archivo_guardado)
    root = Path(current_app.config["UPLOAD_FOLDER"]) / path.parent
    log_activity("download_iso45001_evidence", entity_type="iso45001_evidencia", entity_id=evidence.id)
    return send_from_directory(root, path.name, as_attachment=True, download_name=evidence.archivo_nombre_original)


@bp.route("/documentacion/evidencias/<int:evidence_id>/descargar")
@iso45001_role_required("administrador", "revisor", "evaluador", "respondente", "consulta")
def download_document_evidence(evidence_id: int):
    """Download a shared documentary-evidence file only within its evaluation scope."""

    evidence = Iso45001EvidenciaDocumental.query.get_or_404(evidence_id)
    evaluation = evidence.evaluacion
    if not user_can_view_evaluation(evaluation):
        abort(403)
    path = Path(evidence.archivo_guardado)
    root = Path(current_app.config["UPLOAD_FOLDER"]) / path.parent
    log_activity(
        "download_iso45001_document_evidence",
        entity_type="iso45001_evidencia_documental",
        entity_id=evidence.id,
        metadata={"evaluacion_id": evaluation.id},
    )
    return send_from_directory(root, path.name, as_attachment=True, download_name=evidence.archivo_nombre_original)


def validate_cycle_payload(form_data):
    nombre = clean_text(form_data.get("nombre"))
    descripcion = clean_text(form_data.get("descripcion"))
    estado = clean_text(form_data.get("estado")) or "activo"
    if not nombre:
        return None, "Captura el nombre del ciclo ISO 45001."
    if estado not in ISO45001_CYCLE_STATES:
        return None, "Selecciona un estado válido."
    if Iso45001Ciclo.query.filter_by(nombre=nombre).first():
        return None, "Ya existe un ciclo ISO 45001 con ese nombre."
    try:
        fecha_inicio = date.fromisoformat(form_data.get("fecha_inicio"))
        fecha_cierre = date.fromisoformat(form_data.get("fecha_cierre"))
    except (TypeError, ValueError):
        return None, "Captura fechas válidas para el ciclo."
    if fecha_cierre < fecha_inicio:
        return None, "La fecha de cierre no puede ser anterior al inicio."
    return {
        "nombre": nombre,
        "descripcion": descripcion,
        "estado": estado,
        "fecha_inicio": fecha_inicio,
        "fecha_cierre": fecha_cierre,
    }, None


def create_evaluations_from_form(cycle: Iso45001Ciclo) -> int:
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
        existing = Iso45001Evaluacion.query.filter_by(ciclo_id=cycle.id, dependencia_id=dependency.id).first()
        if existing is not None:
            continue
        evaluation = Iso45001Evaluacion(
            ciclo=cycle,
            dependencia=dependency,
            revisor=revisor,
            estado="borrador",
        )
        db.session.add(evaluation)
        db.session.flush()
        ensure_document_controls_for_evaluation(evaluation, user=current_user)
        if responsable:
            grant_iso_access(responsable)
            db.session.add(Iso45001Asignacion(evaluacion=evaluation, usuario=responsable, tipo="captura"))
        if revisor:
            grant_iso_access(revisor)
        created += 1
    return created


def validate_evaluation_update_payload(form_data, evaluation: Iso45001Evaluacion):
    next_state = clean_text(form_data.get("estado")) or evaluation.estado
    if next_state not in ISO45001_EVALUATION_STATES:
        return None, "Selecciona un estado válido para la evaluación."

    responsable, error = optional_active_user_from_form(form_data.get("responsable_id"), "responsable de captura")
    if error:
        return None, error

    revisor, error = optional_active_user_from_form(
        form_data.get("revisor_id"),
        "revisor",
        allowed_roles={"administrador", "revisor"},
    )
    if error:
        return None, error

    return {
        "estado": next_state,
        "responsable": responsable,
        "revisor": revisor,
    }, None


def _apply_evaluation_update(evaluation: Iso45001Evaluacion, data: dict) -> None:
    sync_evaluation_assignment(evaluation, data["responsable"], data["revisor"])
    evaluation.estado = data["estado"]
    if data["estado"] == "en_revision" and evaluation.enviada_revision_at is None:
        evaluation.enviada_revision_at = utcnow()
    if data["estado"] == "cerrada" and evaluation.cerrada_at is None:
        evaluation.cerrada_at = utcnow()


def optional_active_user_from_form(raw_value, field_label: str, allowed_roles: set[str] | None = None):
    raw_text = clean_text(raw_value)
    if raw_text is None:
        return None, None
    try:
        user_id = int(raw_text)
    except ValueError:
        return None, f"Selecciona un {field_label} válido."
    user = db.session.get(Usuario, user_id)
    if user is None or not user.activo:
        return None, f"Selecciona un {field_label} activo."
    if allowed_roles is not None and user.rol not in allowed_roles:
        return None, f"Selecciona un {field_label} con rol válido."
    return user, None


def sync_evaluation_assignment(evaluation: Iso45001Evaluacion, responsable: Usuario | None, revisor: Usuario | None) -> None:
    evaluation.revisor = revisor
    if evaluation.revisor:
        grant_iso_access(evaluation.revisor)

    capture_assignments = [assignment for assignment in list(evaluation.asignaciones) if assignment.tipo == "captura"]
    for assignment in capture_assignments:
        if responsable is None or assignment.usuario_id != responsable.id:
            db.session.delete(assignment)
    if responsable and not any(assignment.usuario_id == responsable.id for assignment in capture_assignments):
        grant_iso_access(responsable)
        db.session.add(Iso45001Asignacion(evaluacion=evaluation, usuario=responsable, tipo="captura"))


def iso45001_evaluation_has_activity(evaluation: Iso45001Evaluacion) -> bool:
    return bool(evaluation.respuestas or evaluation.observaciones)


def iso45001_cycle_has_activity(cycle: Iso45001Ciclo) -> bool:
    return any(iso45001_evaluation_has_activity(evaluation) for evaluation in cycle.evaluaciones)


def invalid_section_form_options(section) -> list[str]:
    invalid = []
    for reactive in section.reactivos:
        selected = clean_text(request.form.get(f"calificacion_{reactive.id}"))
        if selected is not None and selected not in ISO45001_OPTION_POINTS:
            invalid.append(str(reactive.codigo))
    return invalid


def invalid_section_payload_options(section, payload: dict) -> list[str]:
    section_reactive_ids = {reactive.id for reactive in section.reactivos}
    invalid = []
    for item in payload.get("responses") or []:
        if not isinstance(item, dict):
            invalid.append("respuesta")
            continue
        try:
            reactive_id = int(item.get("reactivo_id"))
        except (TypeError, ValueError):
            invalid.append("reactivo")
            continue
        if reactive_id not in section_reactive_ids:
            invalid.append(str(reactive_id))
            continue
        selected = clean_text(item.get("calificacion"))
        if selected is not None and selected not in ISO45001_OPTION_POINTS:
            invalid.append(str(reactive_id))
    return invalid


def persist_section_from_form(evaluation: Iso45001Evaluacion, section) -> tuple[int, int]:
    response_map = {response.reactivo_id: response for response in evaluation.respuestas}
    saved = 0
    uploaded = 0
    for reactive in section.reactivos:
        selected = clean_text(request.form.get(f"calificacion_{reactive.id}"))
        if selected is None:
            continue
        # The route validates inputs before calling this function.  Keep the
        # defensive guard here so direct callers cannot persist N/A either.
        if selected not in ISO45001_OPTION_POINTS:
            continue
        response = response_map.get(reactive.id)
        if response is None:
            response = Iso45001Respuesta(
                evaluacion=evaluation,
                reactivo=reactive,
                usuario=current_user,
                calificacion=selected,
            )
            db.session.add(response)
            db.session.flush()
            response_map[reactive.id] = response
        response.calificacion = selected
        response.valor = ISO45001_OPTION_POINTS[selected]
        response.observacion = clean_text(request.form.get(f"observacion_{reactive.id}"))
        response.usuario = current_user
        saved += 1
        for upload in request.files.getlist(f"evidencias_{reactive.id}"):
            if not upload or not upload.filename:
                continue
            if not allowed_file(upload.filename):
                flash(f"Archivo rechazado en reactivo {reactive.codigo}: formato no permitido.", "error")
                continue
            size = get_file_size(upload)
            stored = store_upload(upload, f"iso45001/evaluaciones/{evaluation.id}/reactivos/{reactive.id}")
            db.session.add(
                Iso45001Evidencia(
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


def persist_section_from_payload(evaluation: Iso45001Evaluacion, section, payload: dict) -> int:
    response_map = {response.reactivo_id: response for response in evaluation.respuestas}
    section_reactive_ids = {reactive.id for reactive in section.reactivos}
    saved = 0
    for item in payload.get("responses") or []:
        if not isinstance(item, dict):
            continue
        try:
            reactive_id = int(item.get("reactivo_id"))
        except (TypeError, ValueError):
            continue
        if reactive_id not in section_reactive_ids:
            continue
        selected = clean_text(item.get("calificacion"))
        if selected is None or selected not in ISO45001_OPTION_POINTS:
            continue
        response = response_map.get(reactive_id)
        if response is None:
            response = Iso45001Respuesta(
                evaluacion=evaluation,
                reactivo_id=reactive_id,
                usuario=current_user,
                calificacion=selected,
            )
            db.session.add(response)
            response_map[reactive_id] = response
        response.calificacion = selected
        response.valor = ISO45001_OPTION_POINTS[selected]
        response.observacion = clean_text(item.get("observacion"))
        response.usuario = current_user
        saved += 1
    return saved


def latest_section_timestamp(evaluation: Iso45001Evaluacion, section):
    section_reactive_ids = {reactive.id for reactive in section.reactivos}
    timestamps = [
        response.updated_at or response.created_at
        for response in evaluation.respuestas
        if response.reactivo_id in section_reactive_ids
    ]
    return max(timestamps) if timestamps else None


def user_can_view_evaluation(evaluation: Iso45001Evaluacion) -> bool:
    if current_user.rol == "administrador":
        return True
    if any(assignment.usuario_id == current_user.id and assignment.tipo == "captura" for assignment in evaluation.asignaciones):
        return True
    if current_user.rol == "revisor":
        return evaluation.revisor_id == current_user.id or evaluation.estado in ISO45001_FINAL_STATES
    if current_user.rol == "consulta":
        return evaluation.estado in ISO45001_FINAL_STATES
    return any(assignment.usuario_id == current_user.id for assignment in evaluation.asignaciones)


def user_can_edit_evaluation(evaluation: Iso45001Evaluacion) -> bool:
    if not evaluation.editable:
        return False
    if current_user.rol == "administrador":
        return True
    return any(assignment.usuario_id == current_user.id and assignment.tipo == "captura" for assignment in evaluation.asignaciones)


def user_can_review_evaluation(evaluation: Iso45001Evaluacion) -> bool:
    return current_user.rol == "administrador" or evaluation.revisor_id == current_user.id


def get_section_or_404(evaluation: Iso45001Evaluacion, section_id: int):
    for clause in evaluation.ciclo.version.clausulas:
        for section in clause.apartados:
            if section.id == section_id:
                return section
    abort(404)


def select_cycle(cycles: list[Iso45001Ciclo], selected_cycle_id: int | None):
    if not cycles:
        return None
    if selected_cycle_id:
        selected = next((cycle for cycle in cycles if cycle.id == selected_cycle_id), None)
        if selected:
            return selected
    active = next((cycle for cycle in cycles if cycle.estado == "activo"), None)
    return active or cycles[0]


def _normalize_document_controls(raw_controls) -> list[dict]:
    """Normalize the service view for a deliberately thin Jinja template.

    The service remains the source of truth for state and validation. These
    presentation defaults keep a newly-created control clear and safe to
    render, while retaining a harmless compatibility path for catalog v1.
    """

    normalized: list[dict] = []
    for raw in raw_controls:
        data = dict(raw) if isinstance(raw, dict) else {
            key: getattr(raw, key)
            for key in (
                "id", "codigo", "nombre", "clausula", "apartado", "clasificacion", "contenido_minimo",
                "categoria", "estado", "observacion", "evaluated", "puntos", "reactivos", "evidencias",
                "evidence_ids", "puntos_cubiertos", "total_puntos",
            )
            if hasattr(raw, key)
        }
        data["puntos"] = [dict(item) if isinstance(item, dict) else item for item in (data.get("puntos") or [])]
        data["reactivos"] = [dict(item) if isinstance(item, dict) else item for item in (data.get("reactivos") or [])]
        data["evidencias"] = [dict(item) if isinstance(item, dict) else item for item in (data.get("evidencias") or [])]
        data.setdefault("codigo", "Control documental")
        data.setdefault("nombre", data["codigo"])
        data.setdefault("categoria", "normativo" if str(data["codigo"]).startswith("D-") else "complementario")
        data.setdefault("clasificacion", "Información documentada")
        data.setdefault("contenido_minimo", "")
        data.setdefault("clausula", "")
        data.setdefault("apartado", "")
        data.setdefault("observacion", "")
        data.setdefault("estado", "no")
        data.setdefault("evaluated", False)
        data.setdefault("total_puntos", len(data["puntos"]))
        data.setdefault(
            "puntos_cubiertos",
            sum(1 for point in data["puntos"] if _document_value(point, "cubierto", False)),
        )
        evidence_ids = data.get("evidence_ids") or data.get("evidencia_ids") or [
            _document_value(evidence, "id") for evidence in data["evidencias"]
        ]
        data["evidence_ids"] = [int(item) for item in evidence_ids if item is not None]
        state = str(data["estado"] or "no").strip().lower()
        data["estado"] = state
        data["estado_label"] = {
            "no": "No cubierto",
            "parcial": "Cobertura parcial",
            "si": "Cubierto",
        }.get(state, "Sin evaluar")
        data["estado_slug"] = {
            "no": "low",
            "parcial": "medium",
            "si": "high",
        }.get(state, "empty")
        data["requires_file"] = state in {"parcial", "si"}
        normalized.append(data)

    def sort_key(item: dict):
        code = str(item.get("codigo") or "")
        prefix = 0 if code.startswith("D-") else 1
        return prefix, str(item.get("clausula") or "99"), code

    return sorted(normalized, key=sort_key)


def _document_value(value, key: str, default=None):
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _group_document_controls(controls: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = {}
    for control in controls:
        clause = str(control.get("clausula") or "").strip()
        category = str(control.get("categoria") or "").strip()
        if category == "complementario" or not clause:
            key = ("99", "Evidencia complementaria")
        else:
            key = (clause, f"Cláusula {clause}")
        grouped.setdefault(key, []).append(control)

    return [
        {"key": key, "title": title, "controls": items}
        for (key, title), items in sorted(grouped.items(), key=lambda item: _document_group_sort_key(item[0][0]))
    ]


def _document_group_sort_key(value: str):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 99


def _document_control_overview(controls: list[dict]) -> dict:
    total_points = sum(int(item.get("total_puntos") or 0) for item in controls)
    covered_points = sum(int(item.get("puntos_cubiertos") or 0) for item in controls)
    sustained = sum(
        1
        for item in controls
        if item.get("estado") in {"parcial", "si"} and bool(item.get("evidence_ids"))
    )
    evaluated = sum(1 for item in controls if item.get("evaluated"))
    gaps = sum(1 for item in controls if item.get("estado") == "no")
    return {
        "total": len(controls),
        "evaluated": evaluated,
        "covered_points": covered_points,
        "total_points": total_points,
        "percent": round((covered_points / total_points) * 100, 2) if total_points else 0,
        "sustained": sustained,
        "gaps": gaps,
    }


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
    if not user.acceso_iso45001:
        user.acceso_iso45001 = True


def get_file_size(file_storage) -> int:
    stream = file_storage.stream
    position = stream.tell()
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(position)
    return size


def _submission_blocker_message(validation: dict) -> str:
    missing_responses = len(validation["missing_responses"])
    missing_controls = len(validation.get("missing_document_controls") or [])
    missing_control_observations = len(validation.get("missing_control_observations") or [])
    missing_control_evidence = len(validation.get("missing_control_evidence") or [])
    messages = []
    if missing_responses:
        messages.append(f"Debes responder todos los reactivos antes de continuar ({missing_responses} pendientes).")
    if missing_controls:
        messages.append(
            "Debes evaluar todos los controles documentales y grupos complementarios antes de continuar "
            f"({missing_controls} pendientes)."
        )
    if missing_control_observations:
        messages.append(
            "Debes registrar una observación de brecha en cada control documental con resultado No "
            f"({missing_control_observations} pendientes)."
        )
    if missing_control_evidence:
        messages.append(
            "Debes vincular al menos un archivo a cada control documental con resultado Parcial o Sí "
            f"({missing_control_evidence} pendientes)."
        )
    return " ".join(messages)


def _diagnostic_notice() -> str:
    return ISO45001_VERSION.get(
        "aviso_diagnostico",
        "Este diagnóstico es una herramienta de preparación; no constituye una certificación ni sustituye la norma "
        "autorizada o la legislación aplicable.",
    )
