from __future__ import annotations

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
    send_from_directory,
    url_for,
)
from flask_login import current_user

from municipal_diagnostico.decorators import role_required
from municipal_diagnostico.extensions import db
from municipal_diagnostico.models import (
    ComentarioEje,
    EjeVersion,
    EvidenciaEje,
    Evaluacion,
    Respuesta,
    Usuario,
)
from municipal_diagnostico.services.activity_logger import log_activity
from municipal_diagnostico.services.analytics import summarize_evaluation
from municipal_diagnostico.services.notifications import notify_many, notify_user
from municipal_diagnostico.timeutils import to_localtime, utcnow
from municipal_diagnostico.utils import allowed_file, store_upload


bp = Blueprint("evaluation", __name__, url_prefix="/evaluaciones")


@bp.route("/")
@role_required("administrador", "revisor", "evaluador", "consulta")
def index():
    evaluations = Evaluacion.query.order_by(Evaluacion.updated_at.desc()).all()
    if current_user.rol == "administrador":
        filtered = evaluations
    elif current_user.rol == "revisor":
        filtered = [evaluation for evaluation in evaluations if evaluation.revisor_id == current_user.id]
    elif current_user.rol == "consulta":
        filtered = [evaluation for evaluation in evaluations if evaluation.estado in {"aprobada", "cerrada"}]
    else:
        assigned_ids = {assignment.evaluacion_id for assignment in current_user.asignaciones if assignment.tipo == "captura"}
        filtered = [
            evaluation
            for evaluation in evaluations
            if evaluation.dependencia_id == current_user.dependencia_id
            and (not assigned_ids or evaluation.id in assigned_ids)
        ]
    cards = [{"evaluacion": evaluation, "summary": summarize_evaluation(evaluation)} for evaluation in filtered]
    log_activity("view_evaluations_index", metadata={"rol": current_user.rol})
    return render_template("evaluation/list.html", cards=cards)


@bp.route("/<int:evaluation_id>", methods=["GET", "POST"])
@role_required("administrador", "evaluador", "revisor", "consulta")
def detail(evaluation_id: int):
    evaluation = Evaluacion.query.get_or_404(evaluation_id)
    if not user_can_view(evaluation):
        abort(403)

    questionnaire = evaluation.periodo.cuestionario_version

    if request.method == "POST":
        if not user_can_edit(evaluation):
            flash("La evaluación no está disponible para edición.", "error")
            return redirect(url_for("evaluation.detail", evaluation_id=evaluation.id))

        axis_id = request.form.get("eje_id", type=int)
        if axis_id is not None:
            axis = get_axis_or_404(questionnaire.ejes, axis_id)
            saved_count, uploaded_count = persist_axis_from_form(evaluation, axis)
            prepare_evaluation_for_capture(evaluation)
            if evaluation.estado == "devuelta":
                mark_observations_attended(evaluation)
            db.session.commit()
            log_activity(
                "save_axis_module",
                entity_type="evaluacion",
                entity_id=evaluation.id,
                metadata={"eje_id": axis.id, "responses": saved_count, "files": uploaded_count},
            )
            flash("Módulo guardado.", "success")
            return redirect(url_for("evaluation.detail", evaluation_id=evaluation.id, _anchor=f"eje-{axis.id}"))

        for axis in questionnaire.ejes:
            persist_axis_from_form(evaluation, axis)
        prepare_evaluation_for_capture(evaluation)
        if evaluation.estado == "devuelta":
            mark_observations_attended(evaluation)
        db.session.commit()
        log_activity("save_evaluation", entity_type="evaluacion", entity_id=evaluation.id)
        flash("Evaluación guardada.", "success")
        return redirect(url_for("evaluation.detail", evaluation_id=evaluation.id))

    log_activity("view_evaluation_capture", entity_type="evaluacion", entity_id=evaluation.id)
    return render_capture_screen(evaluation, can_edit=user_can_edit(evaluation))


@bp.route("/<int:evaluation_id>/autosave", methods=["POST"])
@role_required("administrador", "evaluador")
def autosave(evaluation_id: int):
    evaluation = Evaluacion.query.get_or_404(evaluation_id)
    if not user_can_edit(evaluation):
        abort(403)

    payload = request.get_json(silent=True) or {}
    axis_id = payload.get("eje_id")
    if axis_id is None:
        return jsonify({"ok": False, "error": "Eje requerido."}), 400

    axis = get_axis_or_404(evaluation.periodo.cuestionario_version.ejes, int(axis_id))
    saved_count = persist_axis_from_payload(evaluation, axis, payload)
    prepare_evaluation_for_capture(evaluation)
    if evaluation.estado == "devuelta":
        mark_observations_attended(evaluation)
    db.session.commit()

    summary = summarize_evaluation(evaluation)
    axis_summary = summary["axis_map"][axis.id]
    comment = next((item for item in evaluation.comentarios_eje if item.eje_version_id == axis.id), None)
    last_saved_at = latest_axis_timestamp(evaluation, axis.id, comment)
    log_activity(
        "autosave_evaluation",
        entity_type="evaluacion",
        entity_id=evaluation.id,
        metadata={"eje_id": axis.id, "responses": saved_count},
    )
    return jsonify(
        {
            "ok": True,
            "completion": summary["completion"],
            "axis_completion": axis_summary["progreso"],
            "last_saved": format_local_timestamp(last_saved_at),
        }
    )


@bp.route("/<int:evaluation_id>/enviar", methods=["POST"])
@role_required("administrador", "evaluador")
def submit(evaluation_id: int):
    evaluation = Evaluacion.query.get_or_404(evaluation_id)
    if not user_can_edit(evaluation):
        abort(403)
    summary = summarize_evaluation(evaluation)
    if summary["completion"] < 100:
        flash("Debes responder todos los reactivos antes de enviar a revisión.", "error")
        return redirect(url_for("evaluation.detail", evaluation_id=evaluation.id))

    evaluation.estado = "en_revision"
    evaluation.enviada_revision_at = utcnow()
    if evaluation.revisor:
        notify_user(
            evaluation.revisor,
            "evaluacion_en_revision",
            f"{evaluation.dependencia.nombre} envió su evaluación del periodo {evaluation.periodo.nombre}.",
            url_for("evaluation.review", evaluation_id=evaluation.id),
        )
    else:
        admins = Usuario.query.filter_by(rol="administrador", activo=True).all()
        notify_many(
            admins,
            "evaluacion_en_revision",
            f"{evaluation.dependencia.nombre} envió una evaluación sin revisor asignado.",
            url_for("admin.evaluation_detail", evaluation_id=evaluation.id),
        )
    db.session.commit()
    log_activity("submit_review", entity_type="evaluacion", entity_id=evaluation.id)
    flash("Evaluación enviada a revisión.", "success")
    return redirect(url_for("dashboard.home"))


@bp.route("/<int:evaluation_id>/revision", methods=["GET", "POST"])
@role_required("administrador", "revisor")
def review(evaluation_id: int):
    evaluation = Evaluacion.query.get_or_404(evaluation_id)
    if not user_can_review(evaluation):
        abort(403)

    if request.method == "POST":
        flash(
            "La revision formal quedo archivada en modo interno de solo lectura.",
            "error",
        )
        return redirect(url_for("evaluation.review", evaluation_id=evaluation.id))

    summary = summarize_evaluation(evaluation)
    log_activity("view_review", entity_type="evaluacion", entity_id=evaluation.id)
    return render_template("evaluation/review.html", evaluacion=evaluation, summary=summary, can_review=True)


@bp.route("/evidencias/<int:evidence_id>/descargar")
@role_required("administrador", "revisor", "evaluador", "consulta")
def download_evidence(evidence_id: int):
    evidence = EvidenciaEje.query.get_or_404(evidence_id)
    if not user_can_view(evidence.evaluacion):
        abort(403)
    path = Path(evidence.archivo_guardado)
    root = Path(current_app.config["UPLOAD_FOLDER"]) / path.parent
    log_activity(
        "download_evidence",
        entity_type="evidencia",
        entity_id=evidence.id,
        metadata={"evaluacion_id": evidence.evaluacion_id, "eje_id": evidence.eje_version_id},
    )
    return send_from_directory(root, path.name, as_attachment=True, download_name=evidence.archivo_nombre_original)


def render_capture_screen(
    evaluation: Evaluacion,
    *,
    can_edit: bool,
    preview_mode: bool = False,
    admin_preview: bool = False,
):
    questionnaire = evaluation.periodo.cuestionario_version
    response_map = {response.reactivo_version_id: response for response in evaluation.respuestas}
    comments = {comment.eje_version_id: comment for comment in evaluation.comentarios_eje}
    evidence_map = {
        axis.id: [
            evidence
            for evidence in evaluation.evidencias
            if evidence.eje_version_id == axis.id and evidence.activo
        ]
        for axis in questionnaire.ejes
    }
    summary = summarize_evaluation(evaluation)
    module_cards = []
    for axis in questionnaire.ejes:
        axis_summary = summary["axis_map"][axis.id]
        comment = comments.get(axis.id)
        module_cards.append(
            {
                "eje": axis,
                "summary": axis_summary,
                "comment": comment,
                "responses": [response_map.get(reactivo.id) for reactivo in axis.reactivos],
                "evidence": evidence_map[axis.id],
                "last_saved": format_local_timestamp(latest_axis_timestamp(evaluation, axis.id, comment)),
            }
        )
    return render_template(
        "evaluation/detail.html",
        evaluacion=evaluation,
        cuestionario=questionnaire,
        respuestas=response_map,
        summary=summary,
        module_cards=module_cards,
        axis_comments=comments,
        evidence_map=evidence_map,
        can_edit=can_edit,
        preview_mode=preview_mode,
        admin_preview=admin_preview,
        hermosillo_timezone=current_app.config.get("APP_TIMEZONE"),
    )


def user_can_view(evaluation: Evaluacion) -> bool:
    if current_user.rol == "administrador":
        return True
    if current_user.rol == "revisor":
        return evaluation.revisor_id == current_user.id or evaluation.estado in {"aprobada", "cerrada"}
    if current_user.rol == "consulta":
        return evaluation.estado in {"aprobada", "cerrada"}
    if current_user.dependencia_id != evaluation.dependencia_id:
        return False
    capture_assignments = [assignment for assignment in evaluation.asignaciones if assignment.tipo == "captura"]
    if not capture_assignments:
        return True
    return any(assignment.usuario_id == current_user.id for assignment in capture_assignments)


def user_can_edit(evaluation: Evaluacion) -> bool:
    return (
        current_user.rol in {"administrador", "evaluador"}
        and user_can_view(evaluation)
        and evaluation.editable
        and evaluation.periodo.esta_abierto
    )


def user_can_review(evaluation: Evaluacion) -> bool:
    if current_user.rol == "administrador":
        return True
    return current_user.rol == "revisor" and evaluation.revisor_id == current_user.id


def evaluation_recipients(evaluation: Evaluacion) -> list[Usuario]:
    recipients = [assignment.usuario for assignment in evaluation.asignaciones if assignment.tipo == "captura"]
    if recipients:
        return recipients
    return Usuario.query.filter_by(
        dependencia_id=evaluation.dependencia_id,
        rol="evaluador",
        activo=True,
    ).all()


def mark_observations_attended(evaluation: Evaluacion) -> None:
    for observation in evaluation.observaciones:
        if not observation.atendida:
            observation.atendida = True
            observation.atendida_at = utcnow()


def persist_axis_from_form(evaluation: Evaluacion, axis: EjeVersion) -> tuple[int, int]:
    response_map = {response.reactivo_version_id: response for response in evaluation.respuestas}
    saved_responses = 0
    for reactivo in axis.reactivos:
        value = request.form.get(f"valor_{reactivo.id}")
        if value is None:
            continue
        response = response_map.get(reactivo.id)
        if response is None:
            response = Respuesta(
                evaluacion=evaluation,
                reactivo_version=reactivo,
                usuario_captura=current_user,
                valor=0,
            )
            db.session.add(response)
        response.valor = int(value)
        response.comentario = clean_text(request.form.get(f"comentario_{reactivo.id}"))
        response.area_id = parse_optional_int(request.form.get(f"area_{reactivo.id}"))
        response.usuario_captura = current_user
        saved_responses += 1

    upsert_axis_comment(
        evaluation,
        axis,
        clean_text(request.form.get(f"comentario_eje_{axis.id}")),
        parse_optional_int(request.form.get(f"comentario_eje_area_{axis.id}")),
    )
    uploaded_count = persist_axis_uploads(
        evaluation,
        axis,
        request.files.getlist(f"evidencias_{axis.id}"),
        parse_optional_int(request.form.get(f"evidencia_area_{axis.id}")),
    )
    return saved_responses, uploaded_count


def persist_axis_from_payload(evaluation: Evaluacion, axis: EjeVersion, payload: dict) -> int:
    response_map = {response.reactivo_version_id: response for response in evaluation.respuestas}
    entries = {int(item["reactivo_id"]): item for item in payload.get("responses", []) if item.get("reactivo_id") is not None}
    saved_responses = 0

    for reactivo in axis.reactivos:
        item = entries.get(reactivo.id)
        if item is None or item.get("valor") in (None, ""):
            continue
        response = response_map.get(reactivo.id)
        if response is None:
            response = Respuesta(
                evaluacion=evaluation,
                reactivo_version=reactivo,
                usuario_captura=current_user,
                valor=0,
            )
            db.session.add(response)
        response.valor = int(item["valor"])
        response.comentario = clean_text(item.get("comentario"))
        response.area_id = parse_optional_int(item.get("area_id"))
        response.usuario_captura = current_user
        saved_responses += 1

    upsert_axis_comment(
        evaluation,
        axis,
        clean_text(payload.get("comentario_eje")),
        parse_optional_int(payload.get("comentario_eje_area_id")),
    )
    return saved_responses


def persist_axis_uploads(
    evaluation: Evaluacion,
    axis: EjeVersion,
    uploads,
    area_id: int | None,
) -> int:
    uploaded_count = 0
    for upload in uploads:
        if not upload or not upload.filename:
            continue
        if not allowed_file(upload.filename):
            flash(f"Archivo rechazado en {axis.nombre}: formato no permitido.", "error")
            continue
        size = get_file_size(upload)
        previous = (
            EvidenciaEje.query.filter_by(
                evaluacion_id=evaluation.id,
                eje_version_id=axis.id,
                archivo_nombre_original=upload.filename,
                activo=True,
            )
            .order_by(EvidenciaEje.version.desc())
            .first()
        )
        if previous:
            previous.activo = False
        stored = store_upload(upload, f"periodos/{evaluation.periodo_id}/evaluaciones/{evaluation.id}")
        db.session.add(
            EvidenciaEje(
                evaluacion=evaluation,
                eje_version=axis,
                area_id=area_id,
                usuario=current_user,
                version=(previous.version + 1) if previous else 1,
                archivo_nombre_original=upload.filename,
                archivo_guardado=stored,
                mime_type=upload.mimetype or "application/octet-stream",
                tamano_bytes=size,
                reemplaza=previous,
                activo=True,
            )
        )
        uploaded_count += 1
    return uploaded_count


def upsert_axis_comment(
    evaluation: Evaluacion,
    axis: EjeVersion,
    comment_text: str | None,
    area_id: int | None,
) -> ComentarioEje:
    comment = next((item for item in evaluation.comentarios_eje if item.eje_version_id == axis.id), None)
    if comment is None:
        comment = ComentarioEje(
            evaluacion=evaluation,
            eje_version=axis,
            usuario=current_user,
        )
        db.session.add(comment)
    comment.comentario = comment_text
    comment.area_id = area_id
    comment.usuario = current_user
    return comment


def prepare_evaluation_for_capture(evaluation: Evaluacion) -> None:
    if evaluation.estado in {"borrador", "devuelta"}:
        evaluation.estado = "en_captura"


def latest_axis_timestamp(
    evaluation: Evaluacion,
    axis_id: int,
    comment: ComentarioEje | None = None,
):
    candidates = [
        response.updated_at
        for response in evaluation.respuestas
        if response.reactivo_version.eje_version_id == axis_id
    ]
    candidates.extend(
        evidence.created_at
        for evidence in evaluation.evidencias
        if evidence.eje_version_id == axis_id and evidence.activo
    )
    if comment and comment.updated_at:
        candidates.append(comment.updated_at)
    if not candidates:
        return None
    return max(candidates)


def format_local_timestamp(value) -> str | None:
    local_value = to_localtime(value)
    if local_value is None:
        return None
    return local_value.strftime("%d/%m/%Y %H:%M")


def get_axis_or_404(axes, axis_id: int) -> EjeVersion:
    axis = next((item for item in axes if item.id == axis_id), None)
    if axis is None:
        abort(404)
    return axis


def parse_optional_int(value) -> int | None:
    if value in (None, "", "None"):
        return None
    return int(value)


def clean_text(value) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def get_file_size(file_storage) -> int:
    file_storage.stream.seek(0, 2)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    return size
