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

from municipal_diagnostico.decorators import role_required
from municipal_diagnostico.extensions import db
from municipal_diagnostico.models import (
    AsignacionCuestionario,
    CampanaCuestionario,
    CuestionarioVersion,
    Dependencia,
    EjeVersion,
    RespuestaAsignacion,
    SoporteSeccion,
    Usuario,
)
from municipal_diagnostico.services.activity_logger import log_activity
from municipal_diagnostico.services.campaign_analytics import (
    ASSIGNMENT_STATE_LABELS,
    CAMPAIGN_STATE_LABELS,
    FINAL_ASSIGNMENT_STATES,
    humanize_assignment_state,
    humanize_campaign_state,
    summarize_assignment,
    summarize_campaign,
)
from municipal_diagnostico.services.exports import build_assignment_excel, build_assignment_pdf, build_assignment_word
from municipal_diagnostico.timeutils import to_localtime, utcnow
from municipal_diagnostico.utils import allowed_file, store_upload


bp = Blueprint("campaigns", __name__, url_prefix="/campanas")


@bp.route("/", methods=["GET", "POST"])
@role_required("administrador")
def index():
    if request.method == "POST":
        action = request.form.get("action")

        if action == "create_campaign":
            data, error = validate_campaign_payload(request.form)
            if error:
                flash(error, "error")
            else:
                campaign = CampanaCuestionario(
                    nombre=data["nombre"],
                    descripcion=data["descripcion"],
                    cuestionario_version=data["cuestionario_version"],
                    fecha_apertura=data["fecha_apertura"],
                    fecha_limite=data["fecha_limite"],
                    estado=data["estado"],
                    creado_por=current_user,
                )
                db.session.add(campaign)
                db.session.commit()
                log_activity("create_campaign", entity_type="campana", entity_id=campaign.id)
                flash("Campana registrada.", "success")

        elif action == "update_campaign":
            campaign = CampanaCuestionario.query.get_or_404(request.form.get("campaign_id", type=int))
            data, error = validate_campaign_payload(request.form, current_campaign=campaign)
            if error:
                flash(error, "error")
            else:
                campaign.nombre = data["nombre"]
                campaign.descripcion = data["descripcion"]
                campaign.cuestionario_version = data["cuestionario_version"]
                campaign.fecha_apertura = data["fecha_apertura"]
                campaign.fecha_limite = data["fecha_limite"]
                campaign.estado = data["estado"]
                db.session.commit()
                log_activity("update_campaign", entity_type="campana", entity_id=campaign.id)
                flash("Campana actualizada.", "success")

        elif action == "change_campaign_state":
            campaign = CampanaCuestionario.query.get_or_404(request.form.get("campaign_id", type=int))
            next_state = clean_text(request.form.get("next_state"))
            if next_state not in CAMPAIGN_STATE_LABELS:
                flash("Selecciona un estado valido.", "error")
            else:
                campaign.estado = next_state
                db.session.commit()
                log_activity(
                    "change_campaign_state",
                    entity_type="campana",
                    entity_id=campaign.id,
                    metadata={"estado": next_state},
                )
                flash("Estado de la campana actualizado.", "success")

        return redirect(url_for("campaigns.index"))

    campaigns = CampanaCuestionario.query.order_by(CampanaCuestionario.created_at.desc()).all()
    questionnaires = CuestionarioVersion.query.order_by(CuestionarioVersion.created_at.desc()).all()
    selected_campaign_id = request.args.get("campana_id", type=int)
    selected_campaign = select_campaign(campaigns, selected_campaign_id)
    selected_summary = summarize_campaign(selected_campaign, role="administrador") if selected_campaign else None
    log_activity("view_campaigns")
    return render_template(
        "campaigns/index.html",
        campaigns=campaigns,
        questionnaires=questionnaires,
        selected_campaign=selected_campaign,
        selected_summary=selected_summary,
        campaign_states=CAMPAIGN_STATE_LABELS,
    )


@bp.route("/asignaciones", methods=["GET", "POST"])
@role_required("administrador", "evaluador", "respondente")
def assignments():
    if request.method == "POST":
        if current_user.rol not in {"administrador"}:
            abort(403)

        action = request.form.get("action")
        if action == "add_assignments":
            campaign = CampanaCuestionario.query.get_or_404(request.form.get("campana_id", type=int))
            created = create_assignments_from_form(campaign)
            db.session.commit()
            log_activity(
                "create_assignment",
                entity_type="campana",
                entity_id=campaign.id,
                metadata={"created": created},
            )
            flash(f"Asignaciones registradas: {created}.", "success" if created else "error")

        elif action == "update_assignment":
            assignment = AsignacionCuestionario.query.get_or_404(request.form.get("assignment_id", type=int))
            respondente_id = request.form.get("respondente_id", type=int)
            next_state = clean_text(request.form.get("estado")) or assignment.estado
            respondente = Usuario.query.get(respondente_id) if respondente_id else None
            if respondente and not respondente.activo:
                flash("El respondente seleccionado esta inactivo.", "error")
            elif next_state not in ASSIGNMENT_STATE_LABELS:
                flash("Selecciona un estado valido.", "error")
            else:
                assignment.respondente = respondente
                assignment.estado = next_state
                if next_state == "cerrado":
                    assignment.cerrada_at = utcnow()
                db.session.commit()
                log_activity(
                    "update_assignment",
                    entity_type="asignacion",
                    entity_id=assignment.id,
                    metadata={"estado": next_state, "respondente_id": respondente_id},
                )
                flash("Asignacion actualizada.", "success")

        elif action == "delete_assignment":
            assignment = AsignacionCuestionario.query.get_or_404(request.form.get("assignment_id", type=int))
            if assignment.respuestas or assignment.soportes:
                flash("No se puede eliminar una asignacion con respuestas o soportes registrados.", "error")
            else:
                assignment_id = assignment.id
                db.session.delete(assignment)
                db.session.commit()
                log_activity("delete_assignment", entity_type="asignacion", entity_id=assignment_id)
                flash("Asignacion eliminada.", "success")

        return redirect(url_for("campaigns.assignments", campana_id=request.form.get("campana_id")))

    selected_campaign_id = request.args.get("campana_id", type=int)
    selected_state = request.args.get("estado", type=str)
    campaigns = CampanaCuestionario.query.order_by(CampanaCuestionario.created_at.desc()).all()
    campaign = select_campaign(campaigns, selected_campaign_id)

    if current_user.rol == "administrador":
        items = AsignacionCuestionario.query.order_by(AsignacionCuestionario.updated_at.desc()).all()
    else:
        items = [
            item
            for item in AsignacionCuestionario.query.order_by(AsignacionCuestionario.updated_at.desc()).all()
            if user_can_view_assignment(item)
        ]

    if campaign:
        items = [item for item in items if item.campana_id == campaign.id]
    if selected_state in ASSIGNMENT_STATE_LABELS:
        items = [item for item in items if item.estado == selected_state]

    cards = [{"asignacion": item, "summary": summarize_assignment(item)} for item in items]
    users = Usuario.query.filter(Usuario.activo.is_(True), Usuario.rol.in_(["administrador", "evaluador", "respondente"])).order_by(Usuario.nombre).all()
    dependencies = Dependencia.query.filter_by(activa=True).order_by(Dependencia.nombre).all()
    log_activity("view_assignments", entity_type="campana", entity_id=campaign.id if campaign else None)
    return render_template(
        "campaigns/assignments.html",
        campaigns=campaigns,
        selected_campaign=campaign,
        selected_state=selected_state,
        assignment_cards=cards,
        users=users,
        dependencies=dependencies,
        assignment_states=ASSIGNMENT_STATE_LABELS,
        current_role=current_user.rol,
    )


@bp.route("/asignaciones/<int:assignment_id>", methods=["GET", "POST"])
@role_required("administrador", "evaluador", "respondente")
def respond(assignment_id: int):
    assignment = AsignacionCuestionario.query.get_or_404(assignment_id)
    if not user_can_view_assignment(assignment):
        abort(403)

    if request.method == "POST":
        if not user_can_edit_assignment(assignment):
            flash("La asignacion no esta disponible para edicion.", "error")
            return redirect(url_for("campaigns.respond", assignment_id=assignment.id))

        axis_id = request.form.get("eje_id", type=int)
        if axis_id is None:
            abort(400)
        axis = get_axis_or_404(assignment.campana.cuestionario_version.ejes, axis_id)
        persist_assignment_axis_form(assignment, axis)
        update_assignment_progress(assignment)
        db.session.commit()
        log_activity(
            "save_assignment_section",
            entity_type="asignacion",
            entity_id=assignment.id,
            metadata={"eje_id": axis.id},
        )
        flash("Seccion guardada.", "success")
        return redirect(url_for("campaigns.respond", assignment_id=assignment.id, _anchor=f"eje-{axis.id}"))

    summary = summarize_assignment(assignment)
    module_cards = build_assignment_modules(assignment, summary)
    log_activity("view_assignment_capture", entity_type="asignacion", entity_id=assignment.id)
    return render_template(
        "campaigns/respond.html",
        asignacion=assignment,
        cuestionario=assignment.campana.cuestionario_version,
        summary=summary,
        module_cards=module_cards,
        can_edit=user_can_edit_assignment(assignment),
    )


@bp.route("/asignaciones/<int:assignment_id>/autosave", methods=["POST"])
@role_required("administrador", "evaluador", "respondente")
def autosave(assignment_id: int):
    assignment = AsignacionCuestionario.query.get_or_404(assignment_id)
    if not user_can_edit_assignment(assignment):
        abort(403)

    payload = request.get_json(silent=True) or {}
    axis_id = payload.get("eje_id")
    if axis_id is None:
        return jsonify({"ok": False, "error": "Seccion requerida."}), 400

    axis = get_axis_or_404(assignment.campana.cuestionario_version.ejes, int(axis_id))
    persist_assignment_axis_payload(assignment, axis, payload)
    update_assignment_progress(assignment)
    db.session.commit()

    summary = summarize_assignment(assignment)
    axis_summary = summary["axis_map"][axis.id]
    last_saved = latest_assignment_axis_timestamp(assignment, axis.id)
    log_activity(
        "autosave_assignment",
        entity_type="asignacion",
        entity_id=assignment.id,
        metadata={"eje_id": axis.id},
    )
    return jsonify(
        {
            "ok": True,
            "completion": summary["completion"],
            "axis_completion": axis_summary["progreso"],
            "last_saved": format_local_timestamp(last_saved),
        }
    )


@bp.route("/asignaciones/<int:assignment_id>/enviar", methods=["POST"])
@role_required("administrador", "evaluador", "respondente")
def submit(assignment_id: int):
    assignment = AsignacionCuestionario.query.get_or_404(assignment_id)
    if not user_can_edit_assignment(assignment):
        abort(403)

    summary = summarize_assignment(assignment)
    if summary["completion"] < 100:
        flash("Debes responder todos los reactivos antes de enviar el cuestionario.", "error")
        return redirect(url_for("campaigns.respond", assignment_id=assignment.id))

    assignment.estado = "respondido"
    assignment.fecha_envio = utcnow()
    assignment.progreso = 100
    assignment.ultima_actividad_at = utcnow()
    db.session.commit()
    log_activity("submit_assignment", entity_type="asignacion", entity_id=assignment.id)
    flash("Cuestionario enviado.", "success")
    return redirect(url_for("campaigns.assignments"))


@bp.route("/soportes/<int:support_id>/descargar")
@role_required("administrador", "evaluador", "respondente", "consulta")
def download_support(support_id: int):
    support = SoporteSeccion.query.get_or_404(support_id)
    if not user_can_view_assignment(support.asignacion):
        abort(403)
    if not support.archivo_guardado:
        abort(404)
    path = Path(support.archivo_guardado)
    root = Path(current_app.config["UPLOAD_FOLDER"]) / path.parent
    log_activity(
        "download_section_support",
        entity_type="soporte",
        entity_id=support.id,
        metadata={"asignacion_id": support.asignacion_id, "eje_id": support.eje_version_id},
    )
    return send_from_directory(root, path.name, as_attachment=True, download_name=support.archivo_nombre_original)


@bp.route("/reportes")
@role_required("administrador", "evaluador", "respondente", "consulta")
def reports():
    selected_campaign_id = request.args.get("campana_id", type=int)
    campaigns = campaign_query_for_role(current_user.rol)
    selected_campaign = select_campaign(campaigns, selected_campaign_id)
    selected_summary = summarize_campaign(selected_campaign, role=current_user.rol) if selected_campaign else None
    log_activity("view_campaign_reports", entity_type="campana", entity_id=selected_campaign.id if selected_campaign else None)
    return render_template(
        "campaigns/reports.html",
        campaigns=campaigns,
        selected_campaign=selected_campaign,
        selected_summary=selected_summary,
        assignment_states=ASSIGNMENT_STATE_LABELS,
    )


@bp.route("/reportes/asignaciones/<int:assignment_id>")
@role_required("administrador", "evaluador", "respondente", "consulta")
def assignment_report(assignment_id: int):
    assignment = AsignacionCuestionario.query.get_or_404(assignment_id)
    if not user_can_view_assignment(assignment):
        abort(403)
    summary = summarize_assignment(assignment)
    module_cards = build_assignment_modules(assignment, summary)
    log_activity("view_assignment_report", entity_type="asignacion", entity_id=assignment.id)
    return render_template(
        "campaigns/assignment_report.html",
        asignacion=assignment,
        summary=summary,
        module_cards=module_cards,
    )


@bp.route("/reportes/asignaciones/<int:assignment_id>/pdf")
@role_required("administrador", "evaluador", "respondente", "consulta")
def assignment_pdf(assignment_id: int):
    assignment = AsignacionCuestionario.query.get_or_404(assignment_id)
    if not user_can_view_assignment(assignment):
        abort(403)
    buffer = build_assignment_pdf(assignment)
    log_activity("export_pdf", entity_type="asignacion", entity_id=assignment.id)
    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"reporte-asignacion-{assignment.id}.pdf",
    )


@bp.route("/reportes/asignaciones/<int:assignment_id>/xlsx")
@role_required("administrador", "evaluador", "respondente", "consulta")
def assignment_excel(assignment_id: int):
    assignment = AsignacionCuestionario.query.get_or_404(assignment_id)
    if not user_can_view_assignment(assignment):
        abort(403)
    buffer = build_assignment_excel(assignment)
    log_activity("export_excel", entity_type="asignacion", entity_id=assignment.id)
    return send_file(
        buffer,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"reporte-asignacion-{assignment.id}.xlsx",
    )


@bp.route("/reportes/asignaciones/<int:assignment_id>/word")
@role_required("administrador", "evaluador", "respondente", "consulta")
def assignment_word(assignment_id: int):
    assignment = AsignacionCuestionario.query.get_or_404(assignment_id)
    if not user_can_view_assignment(assignment):
        abort(403)
    buffer = build_assignment_word(assignment)
    log_activity("export_word", entity_type="asignacion", entity_id=assignment.id)
    return send_file(
        buffer,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=f"reporte-asignacion-{assignment.id}.docx",
    )


def campaign_query_for_role(role: str) -> list[CampanaCuestionario]:
    query = CampanaCuestionario.query.order_by(CampanaCuestionario.created_at.desc())
    items = query.all()
    if role == "consulta":
        return [campaign for campaign in items if campaign.estado in {"activa", "cerrada"}]
    if role in {"evaluador", "respondente"}:
        visible_ids = {assignment.campana_id for assignment in user_visible_assignments()}
        return [campaign for campaign in items if campaign.id in visible_ids]
    return items


def user_visible_assignments() -> list[AsignacionCuestionario]:
    items = AsignacionCuestionario.query.order_by(AsignacionCuestionario.updated_at.desc()).all()
    return [item for item in items if user_can_view_assignment(item)]


def select_campaign(campaigns: list[CampanaCuestionario], selected_campaign_id: int | None):
    if not campaigns:
        return None
    if selected_campaign_id:
        selected = next((campaign for campaign in campaigns if campaign.id == selected_campaign_id), None)
        if selected:
            return selected
    active = next((campaign for campaign in campaigns if campaign.estado == "activa"), None)
    return active or campaigns[0]


def validate_campaign_payload(form_data, current_campaign: CampanaCuestionario | None = None):
    nombre = clean_text(form_data.get("nombre"))
    descripcion = clean_text(form_data.get("descripcion"))
    estado = clean_text(form_data.get("estado")) or "borrador"
    cuestionario_version_id = form_data.get("cuestionario_version_id", type=int)
    fecha_apertura = form_data.get("fecha_apertura")
    fecha_limite = form_data.get("fecha_limite")

    if not nombre:
        return None, "Captura el nombre de la campana."
    if estado not in CAMPAIGN_STATE_LABELS:
        return None, "Selecciona un estado valido."
    cuestionario = CuestionarioVersion.query.get(cuestionario_version_id) if cuestionario_version_id else None
    if cuestionario is None:
        return None, "Selecciona una version de cuestionario."

    existing = CampanaCuestionario.query.filter_by(nombre=nombre).first()
    if existing and (current_campaign is None or existing.id != current_campaign.id):
        return None, "Ya existe una campana con ese nombre."

    try:
        opening = date.fromisoformat(fecha_apertura)
        deadline = date.fromisoformat(fecha_limite)
    except Exception:
        return None, "Captura fechas validas para apertura y limite."

    if deadline < opening:
        return None, "La fecha limite no puede ser anterior a la apertura."
    if current_campaign and current_campaign.asignaciones and current_campaign.cuestionario_version_id != cuestionario.id:
        return None, "No puedes cambiar el cuestionario de una campana que ya tiene asignaciones."

    return {
        "nombre": nombre,
        "descripcion": descripcion,
        "estado": estado,
        "cuestionario_version": cuestionario,
        "fecha_apertura": opening,
        "fecha_limite": deadline,
    }, None


def create_assignments_from_form(campaign: CampanaCuestionario) -> int:
    created = 0
    default_respondente_id = request.form.get("respondente_id", type=int)
    default_respondente = Usuario.query.get(default_respondente_id) if default_respondente_id else None
    user_ids = [int(value) for value in request.form.getlist("usuario_ids") if value]
    dependency_ids = [int(value) for value in request.form.getlist("dependencia_ids") if value]

    for user_id in user_ids:
        user = Usuario.query.get(user_id)
        if user is None:
            continue
        existing = find_assignment(campaign.id, "usuario", user_id=user.id)
        if existing:
            continue
        db.session.add(
            AsignacionCuestionario(
                campana=campaign,
                target_type="usuario",
                usuario=user,
                dependencia=user.dependencia,
                respondente=user,
                estado="pendiente",
            )
        )
        created += 1

    for dependency_id in dependency_ids:
        dependency = Dependencia.query.get(dependency_id)
        if dependency is None:
            continue
        existing = find_assignment(campaign.id, "dependencia", dependencia_id=dependency.id)
        if existing:
            continue
        db.session.add(
            AsignacionCuestionario(
                campana=campaign,
                target_type="dependencia",
                dependencia=dependency,
                respondente=default_respondente,
                estado="pendiente",
            )
        )
        created += 1

    return created


def find_assignment(campaign_id: int, target_type: str, *, user_id: int | None = None, dependencia_id: int | None = None):
    query = AsignacionCuestionario.query.filter_by(campana_id=campaign_id, target_type=target_type)
    if user_id is not None:
        query = query.filter_by(usuario_id=user_id)
    if dependencia_id is not None:
        query = query.filter_by(dependencia_id=dependencia_id)
    return query.first()


def user_can_view_assignment(assignment: AsignacionCuestionario) -> bool:
    if current_user.rol == "administrador":
        return True
    if current_user.rol == "consulta":
        return assignment.estado in FINAL_ASSIGNMENT_STATES and assignment.campana.estado in {"activa", "cerrada"}
    return (
        assignment.respondente_id == current_user.id
        or assignment.usuario_id == current_user.id
    )


def user_can_edit_assignment(assignment: AsignacionCuestionario) -> bool:
    if current_user.rol == "administrador":
        return assignment.campana.estado in {"borrador", "activa"} and assignment.estado != "cerrado"
    return user_can_view_assignment(assignment) and assignment.puede_responder


def build_assignment_modules(assignment: AsignacionCuestionario, summary: dict) -> list[dict]:
    response_map = {response.reactivo_version_id: response for response in assignment.respuestas}
    support_map = {support.eje_version_id: support for support in assignment.soportes}
    cards = []
    for axis in assignment.campana.cuestionario_version.ejes:
        cards.append(
            {
                "eje": axis,
                "summary": summary["axis_map"][axis.id],
                "responses": [response_map.get(reactivo.id) for reactivo in axis.reactivos],
                "support": support_map.get(axis.id),
                "last_saved": format_local_timestamp(latest_assignment_axis_timestamp(assignment, axis.id)),
            }
        )
    return cards


def persist_assignment_axis_form(assignment: AsignacionCuestionario, axis: EjeVersion) -> None:
    response_map = {response.reactivo_version_id: response for response in assignment.respuestas}
    for reactivo in axis.reactivos:
        value = request.form.get(f"valor_{reactivo.id}")
        if value is None:
            continue
        response = response_map.get(reactivo.id)
        if response is None:
            response = RespuestaAsignacion(
                asignacion=assignment,
                reactivo_version=reactivo,
                usuario=current_user,
                valor=0,
            )
            db.session.add(response)
        response.valor = int(value)
        response.comentario = clean_text(request.form.get(f"comentario_{reactivo.id}"))
        response.usuario = current_user

    upsert_section_support(
        assignment,
        axis,
        clean_text(request.form.get(f"comentario_eje_{axis.id}")),
        request.files.get(f"evidencia_{axis.id}"),
    )


def persist_assignment_axis_payload(assignment: AsignacionCuestionario, axis: EjeVersion, payload: dict) -> None:
    response_map = {response.reactivo_version_id: response for response in assignment.respuestas}
    entries = {
        int(item["reactivo_id"]): item
        for item in payload.get("responses", [])
        if item.get("reactivo_id") is not None
    }

    for reactivo in axis.reactivos:
        item = entries.get(reactivo.id)
        if item is None or item.get("valor") in (None, ""):
            continue
        response = response_map.get(reactivo.id)
        if response is None:
            response = RespuestaAsignacion(
                asignacion=assignment,
                reactivo_version=reactivo,
                usuario=current_user,
                valor=0,
            )
            db.session.add(response)
        response.valor = int(item["valor"])
        response.comentario = clean_text(item.get("comentario"))
        response.usuario = current_user

    upsert_section_support(
        assignment,
        axis,
        clean_text(payload.get("comentario_eje")),
        None,
    )


def upsert_section_support(
    assignment: AsignacionCuestionario,
    axis: EjeVersion,
    comment_text: str | None,
    upload,
) -> SoporteSeccion:
    support = next((item for item in assignment.soportes if item.eje_version_id == axis.id), None)
    if support is None:
        support = SoporteSeccion(
            asignacion=assignment,
            eje_version=axis,
            usuario=current_user,
        )
        db.session.add(support)

    support.comentario = comment_text
    support.usuario = current_user

    if upload and upload.filename:
        if not allowed_file(upload.filename):
            flash(f"Archivo rechazado en {axis.nombre}: formato no permitido.", "error")
        else:
            stored = store_upload(upload, f"campanas/{assignment.campana_id}/asignaciones/{assignment.id}")
            support.archivo_nombre_original = upload.filename
            support.archivo_guardado = stored
            support.mime_type = upload.mimetype or "application/octet-stream"
            support.tamano_bytes = get_file_size(upload)
    return support


def update_assignment_progress(assignment: AsignacionCuestionario) -> None:
    summary = summarize_assignment(assignment)
    assignment.progreso = summary["completion"]
    assignment.ultima_actividad_at = utcnow()
    if assignment.respondente is None and current_user.is_authenticated:
        assignment.respondente = current_user
    if summary["completion"] > 0 and assignment.estado == "pendiente":
        assignment.estado = "en_progreso"
        assignment.fecha_inicio = assignment.fecha_inicio or utcnow()
    if assignment.estado in FINAL_ASSIGNMENT_STATES and summary["completion"] < 100:
        assignment.estado = "en_progreso"


def latest_assignment_axis_timestamp(assignment: AsignacionCuestionario, axis_id: int):
    candidates = [
        response.updated_at
        for response in assignment.respuestas
        if response.reactivo_version.eje_version_id == axis_id
    ]
    candidates.extend(
        support.updated_at
        for support in assignment.soportes
        if support.eje_version_id == axis_id
    )
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
