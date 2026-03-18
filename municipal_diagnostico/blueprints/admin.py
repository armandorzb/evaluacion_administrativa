from __future__ import annotations

from collections import Counter
from datetime import datetime, time

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from municipal_diagnostico.decorators import role_required
from municipal_diagnostico.extensions import db
from municipal_diagnostico.models import (
    ActividadPlataforma,
    Area,
    ComentarioEje,
    CuestionarioVersion,
    Dependencia,
    EvidenciaEje,
    Evaluacion,
    Notificacion,
    PeriodoEvaluacion,
    ReactivoVersion,
    Respuesta,
    SesionPlataforma,
    Usuario,
)
from municipal_diagnostico.seeds import (
    clone_questionnaire_version,
    ensure_official_questionnaire,
)
from municipal_diagnostico.services.activity_logger import log_activity
from municipal_diagnostico.services.analytics import REPORTABLE_EVALUATION_STATES, summarize_evaluation
from municipal_diagnostico.services.importers import (
    import_areas,
    import_dependencias,
    import_usuarios,
    load_rows,
)
from municipal_diagnostico.services.notifications import notify_user
from municipal_diagnostico.timeutils import to_utc_naive, utcnow


bp = Blueprint("admin", __name__, url_prefix="/admin")


ACTIVITY_LABELS = {
    "login_success": "Inicio de sesión",
    "logout": "Cierre de sesión",
    "view_dashboard": "Consulta de tablero",
    "view_monitoring": "Consulta de monitoreo",
    "view_evaluation_capture": "Apertura de captura",
    "view_evaluation_report": "Consulta de reporte",
    "view_evaluations_index": "Consulta de evaluaciones",
    "view_review": "Consulta de revisión",
    "view_reports_hub": "Consulta de hub operativo",
    "view_executive_home": "Consulta de centro ejecutivo",
    "view_executive_dependency": "Consulta ejecutiva por dependencia",
    "view_executive_axis": "Consulta ejecutiva por eje",
    "view_period_report": "Consulta de reporte de periodo",
    "view_periods": "Consulta de periodos",
    "view_questionnaires": "Consulta de cuestionarios",
    "view_catalogs": "Consulta de catálogos",
    "view_questionnaire_editor": "Edición de cuestionario",
    "view_questionnaire_fill_preview": "Vista de llenado",
    "view_implementation_preview": "Vista de implementación",
    "view_admin_evaluation": "Gestión de evaluación",
    "view_as_evaluator": "Vista capturista operativa",
    "view_evaluator_views": "Listado de captura operativa",
    "read_notification": "Lectura de notificación",
    "autosave_evaluation": "Autoguardado",
    "save_axis_module": "Guardado de módulo",
    "save_evaluation": "Guardado de evaluación",
    "submit_review": "Envío a revisión",
    "approve_evaluation": "Aprobación de evaluación",
    "return_evaluation": "Devolución con observaciones",
    "assign_reviewer": "Asignación de revisor",
    "assign_evaluator": "Asignación de capturista",
    "download_evidence": "Descarga de evidencia",
    "export_pdf": "Exportación PDF",
    "export_excel": "Exportación Excel",
    "export_word": "Exportación Word",
    "export_csv": "Exportación CSV",
    "create_period": "Creación de periodo",
    "open_period": "Apertura de periodo",
    "close_period": "Cierre de periodo",
    "reopen_period": "Reapertura de periodo",
    "create_dependency": "Alta de dependencia",
    "create_area": "Alta de área",
    "create_user": "Alta de usuario",
    "update_dependency": "Actualización de dependencia",
    "update_area": "Actualización de unidad administrativa",
    "update_user": "Actualización de usuario",
    "delete_dependency": "Eliminación de dependencia",
    "delete_area": "Eliminación de unidad administrativa",
    "delete_user": "Eliminación de usuario",
    "bulk_import": "Carga masiva",
    "view_campaigns": "Consulta de campanas",
    "create_campaign": "Alta de campana",
    "update_campaign": "Actualizacion de campana",
    "change_campaign_state": "Cambio de estado de campana",
    "view_assignments": "Consulta de asignaciones",
    "create_assignment": "Alta de asignaciones",
    "update_assignment": "Actualizacion de asignacion",
    "delete_assignment": "Eliminacion de asignacion",
    "view_assignment_capture": "Apertura de cuestionario asignado",
    "autosave_assignment": "Autoguardado de asignacion",
    "save_assignment_section": "Guardado de seccion",
    "submit_assignment": "Envio de cuestionario",
    "download_section_support": "Descarga de soporte por seccion",
    "view_campaign_reports": "Consulta de reportes de campana",
    "view_assignment_report": "Consulta de reporte de asignacion",
    "clone_questionnaire": "Clonado de cuestionario",
    "publish_questionnaire": "Publicación de cuestionario",
    "archive_questionnaire": "Archivado de cuestionario",
    "update_questionnaire": "Actualización de cuestionario",
    "add_reactive": "Alta de reactivo",
    "delete_reactive": "Eliminación de reactivo",
}

ROLE_DEFINITIONS = {
    "administrador": "Administra catálogos, periodos, cuestionarios, reportes, monitoreo y configuración general de la plataforma.",
    "revisor": "Valida evaluaciones enviadas, devuelve observaciones y aprueba resultados antes del cierre formal.",
    "evaluador": "Captura el cuestionario, asigna responsables operativos, registra comentarios y adjunta evidencia documental.",
    "respondente": "Responde cuestionarios asignados, guarda avance parcial y registra soportes opcionales por seccion.",
    "consulta": "Accede a tableros y resultados oficiales en modo de solo lectura, sin permisos de edición.",
}


@bp.route("/catalogos", methods=["GET", "POST"])
@role_required("administrador")
def catalogs():
    if request.method == "POST":
        action = request.form.get("action")
        redirect_anchor = request.form.get("redirect_anchor") or "catalogo-usuarios"

        if action == "add_dependencia":
            nombre = clean_catalog_text(request.form.get("nombre"))
            tipo = clean_catalog_text(request.form.get("tipo")) or "Administrativa"
            descripcion = clean_catalog_text(request.form.get("descripcion"))

            if not nombre:
                flash("Captura el nombre de la dependencia.", "error")
            elif dependency_name_exists(nombre):
                flash("Ya existe una dependencia con ese nombre.", "error")
            else:
                dependency = Dependencia(
                    nombre=nombre,
                    tipo=tipo,
                    descripcion=descripcion,
                    activa=True,
                )
                db.session.add(dependency)
                db.session.commit()
                log_activity("create_dependency", entity_type="dependencia", entity_id=dependency.id)
                flash("Dependencia registrada.", "success")
                redirect_anchor = "catalogo-dependencias"

        elif action == "update_dependencia":
            dependency = db.session.get(Dependencia, request.form.get("dependencia_id", type=int))
            if dependency is None:
                flash("La dependencia solicitada no existe.", "error")
            else:
                nombre = clean_catalog_text(request.form.get("nombre"))
                tipo = clean_catalog_text(request.form.get("tipo")) or "Administrativa"
                descripcion = clean_catalog_text(request.form.get("descripcion"))
                if not nombre:
                    flash("Captura el nombre de la dependencia.", "error")
                elif dependency_name_exists(nombre, current_id=dependency.id):
                    flash("Ya existe otra dependencia con ese nombre.", "error")
                else:
                    dependency.nombre = nombre
                    dependency.tipo = tipo
                    dependency.descripcion = descripcion
                    db.session.commit()
                    log_activity("update_dependency", entity_type="dependencia", entity_id=dependency.id)
                    flash("Dependencia actualizada.", "success")
                redirect_anchor = "catalogo-dependencias"

        elif action == "toggle_dependencia":
            dependency = db.session.get(Dependencia, request.form.get("dependencia_id", type=int))
            if dependency is None:
                flash("La dependencia solicitada no existe.", "error")
            else:
                dependency.activa = not dependency.activa
                if not dependency.activa:
                    for area in dependency.areas:
                        area.activa = False
                db.session.commit()
                flash(
                    "Dependencia activada." if dependency.activa else "Dependencia desactivada. Sus unidades administrativas quedaron inactivas.",
                    "success",
                )
                log_activity("update_dependency", entity_type="dependencia", entity_id=dependency.id, metadata={"activa": dependency.activa})
                redirect_anchor = "catalogo-dependencias"

        elif action == "delete_dependencia":
            dependency = db.session.get(Dependencia, request.form.get("dependencia_id", type=int))
            if dependency is None:
                flash("La dependencia solicitada no existe.", "error")
            else:
                blockers = dependency_delete_blockers(dependency)
                if blockers:
                    flash(f"No se puede eliminar la dependencia: {', '.join(blockers)}.", "error")
                else:
                    dependency_id = dependency.id
                    db.session.delete(dependency)
                    db.session.commit()
                    log_activity("delete_dependency", entity_type="dependencia", entity_id=dependency_id)
                    flash("Dependencia eliminada.", "success")
                redirect_anchor = "catalogo-dependencias"

        elif action == "add_area":
            nombre = clean_catalog_text(request.form.get("nombre"))
            dependencia_id = request.form.get("dependencia_id", type=int)
            dependency = db.session.get(Dependencia, dependencia_id) if dependencia_id else None
            if dependency is None:
                flash("Selecciona una dependencia válida para la unidad administrativa.", "error")
            elif not nombre:
                flash("Captura el nombre de la unidad administrativa.", "error")
            elif area_name_exists(dependency.id, nombre):
                flash("Ya existe una unidad administrativa con ese nombre en la dependencia seleccionada.", "error")
            else:
                area = Area(
                    nombre=nombre,
                    dependencia=dependency,
                    activa=True,
                )
                db.session.add(area)
                db.session.commit()
                log_activity("create_area", entity_type="area", entity_id=area.id)
                flash("Unidad administrativa registrada.", "success")
                redirect_anchor = "catalogo-areas"

        elif action == "update_area":
            area = db.session.get(Area, request.form.get("area_id", type=int))
            if area is None:
                flash("La unidad administrativa solicitada no existe.", "error")
            else:
                nombre = clean_catalog_text(request.form.get("nombre"))
                dependencia_id = request.form.get("dependencia_id", type=int)
                dependency = db.session.get(Dependencia, dependencia_id) if dependencia_id else None
                if dependency is None:
                    flash("Selecciona una dependencia válida.", "error")
                elif not nombre:
                    flash("Captura el nombre de la unidad administrativa.", "error")
                elif area_name_exists(dependency.id, nombre, current_id=area.id):
                    flash("Ya existe otra unidad administrativa con ese nombre en la dependencia seleccionada.", "error")
                elif dependency.id != area.dependencia_id and area_has_operational_data(area):
                    flash("No se puede mover la unidad administrativa porque ya tiene información operativa relacionada.", "error")
                else:
                    area.nombre = nombre
                    area.dependencia = dependency
                    db.session.commit()
                    log_activity("update_area", entity_type="area", entity_id=area.id)
                    flash("Unidad administrativa actualizada.", "success")
                redirect_anchor = "catalogo-areas"

        elif action == "toggle_area":
            area = db.session.get(Area, request.form.get("area_id", type=int))
            if area is None:
                flash("La unidad administrativa solicitada no existe.", "error")
            else:
                area.activa = not area.activa
                db.session.commit()
                flash("Unidad administrativa activada." if area.activa else "Unidad administrativa desactivada.", "success")
                log_activity("update_area", entity_type="area", entity_id=area.id, metadata={"activa": area.activa})
                redirect_anchor = "catalogo-areas"

        elif action == "delete_area":
            area = db.session.get(Area, request.form.get("area_id", type=int))
            if area is None:
                flash("La unidad administrativa solicitada no existe.", "error")
            else:
                blockers = area_delete_blockers(area)
                if blockers:
                    flash(f"No se puede eliminar la unidad administrativa: {', '.join(blockers)}.", "error")
                else:
                    area_id = area.id
                    db.session.delete(area)
                    db.session.commit()
                    log_activity("delete_area", entity_type="area", entity_id=area_id)
                    flash("Unidad administrativa eliminada.", "success")
                redirect_anchor = "catalogo-areas"

        elif action == "add_usuario":
            user_data, error_message = validate_user_payload(request.form)
            if error_message:
                flash(error_message, "error")
            else:
                user = Usuario(
                    nombre=user_data["nombre"],
                    correo=user_data["correo"],
                    rol=user_data["rol"],
                    dependencia_id=user_data["dependencia_id"],
                    area_id=user_data["area_id"],
                    activo=True,
                )
                user.set_password(user_data["password"])
                db.session.add(user)
                db.session.commit()
                log_activity("create_user", entity_type="usuario", entity_id=user.id, metadata={"rol": user.rol})
                flash("Usuario creado.", "success")
                redirect_anchor = "catalogo-usuarios"

        elif action == "update_usuario":
            user = db.session.get(Usuario, request.form.get("usuario_id", type=int))
            if user is None:
                flash("El usuario solicitado no existe.", "error")
            else:
                user_data, error_message = validate_user_payload(request.form, current_user_id=user.id, password_required=False)
                next_role = user_data["rol"] if not error_message else user.rol
                if error_message:
                    flash(error_message, "error")
                elif would_remove_last_active_admin(user, next_role=next_role, next_active=user.activo):
                    flash("Debe existir al menos un administrador activo en la plataforma.", "error")
                else:
                    user.nombre = user_data["nombre"]
                    user.correo = user_data["correo"]
                    user.rol = user_data["rol"]
                    user.dependencia_id = user_data["dependencia_id"]
                    user.area_id = user_data["area_id"]
                    if user_data["password"]:
                        user.set_password(user_data["password"])
                    db.session.commit()
                    log_activity("update_user", entity_type="usuario", entity_id=user.id, metadata={"rol": user.rol})
                    flash("Usuario actualizado.", "success")
                redirect_anchor = "catalogo-usuarios"

        elif action == "toggle_usuario":
            user = db.session.get(Usuario, request.form.get("usuario_id", type=int))
            if user is None:
                flash("El usuario solicitado no existe.", "error")
            elif would_remove_last_active_admin(user, next_active=not user.activo):
                flash("Debe existir al menos un administrador activo en la plataforma.", "error")
            else:
                user.activo = not user.activo
                db.session.commit()
                flash("Usuario activado." if user.activo else "Usuario desactivado.", "success")
                log_activity("update_user", entity_type="usuario", entity_id=user.id, metadata={"activo": user.activo})
                redirect_anchor = "catalogo-usuarios"

        elif action == "delete_usuario":
            user = db.session.get(Usuario, request.form.get("usuario_id", type=int))
            if user is None:
                flash("El usuario solicitado no existe.", "error")
            elif would_remove_last_active_admin(user, next_role=None, next_active=False, deleting=True):
                flash("Debe existir al menos un administrador activo en la plataforma.", "error")
            else:
                blockers = user_delete_blockers(user)
                if blockers:
                    flash(f"No se puede eliminar el usuario: {', '.join(blockers)}. Puedes desactivarlo en su lugar.", "error")
                else:
                    user_id = user.id
                    db.session.delete(user)
                    db.session.commit()
                    log_activity("delete_user", entity_type="usuario", entity_id=user_id)
                    flash("Usuario eliminado.", "success")
                redirect_anchor = "catalogo-usuarios"

        elif action == "bulk_import":
            import_type = request.form.get("import_type")
            upload = request.files.get("archivo")
            if not upload or not upload.filename:
                flash("Selecciona un archivo CSV o Excel.", "error")
            else:
                rows = load_rows(upload)
                if import_type == "dependencias":
                    result = import_dependencias(rows)
                elif import_type == "areas":
                    result = import_areas(rows)
                else:
                    result = import_usuarios(rows)
                log_activity(
                    "bulk_import",
                    metadata={
                        "tipo": import_type,
                        "created": result["created"],
                        "updated": result["updated"],
                        "errors": len(result["errors"]),
                    },
                )
                flash(
                    f"Carga completada. Nuevos: {result['created']} | Actualizados: {result['updated']} | Errores: {len(result['errors'])}",
                    "success" if not result["errors"] else "error",
                )
            redirect_anchor = "catalogo-importacion"

        return redirect(f"{url_for('admin.catalogs')}#{redirect_anchor}")

    dependencies = Dependencia.query.order_by(Dependencia.nombre).all()
    areas = Area.query.join(Dependencia).order_by(Dependencia.nombre, Area.nombre).all()
    users = Usuario.query.order_by(Usuario.nombre).all()
    active_dependencies = [dependency for dependency in dependencies if dependency.activa]
    active_areas = [area for area in areas if area.activa and area.dependencia.activa]
    stats = {
        "dependencias_activas": sum(1 for dependency in dependencies if dependency.activa),
        "areas_activas": sum(1 for area in areas if area.activa),
        "usuarios_activos": sum(1 for user in users if user.activo),
        "administradores_activos": sum(1 for user in users if user.activo and user.rol == "administrador"),
    }
    log_activity("view_catalogs")
    return render_template(
        "admin/catalogs.html",
        dependencias=dependencies,
        areas=areas,
        usuarios=users,
        dependencias_activas=active_dependencies,
        areas_activas=active_areas,
        role_definitions=ROLE_DEFINITIONS,
        stats=stats,
    )


@bp.route("/cuestionarios", methods=["GET", "POST"])
@role_required("administrador")
def questionnaires():
    ensure_official_questionnaire()
    if request.method == "POST":
        action = request.form.get("action")
        version_id = request.form.get("version_id")
        version = CuestionarioVersion.query.get(version_id) if version_id else None

        if action == "clone" and version:
            cloned = clone_questionnaire_version(
                version,
                creado_por=current_user,
                nombre=request.form.get("nombre") or f"{version.nombre} - borrador",
            )
            db.session.commit()
            log_activity("clone_questionnaire", entity_type="cuestionario", entity_id=cloned.id)
            flash("Versión clonada en borrador.", "success")
            return redirect(url_for("admin.edit_questionnaire", version_id=cloned.id))
        if action == "publish" and version:
            version.estado = "publicado"
            version.publicado_at = utcnow()
            db.session.commit()
            log_activity("publish_questionnaire", entity_type="cuestionario", entity_id=version.id)
            flash("Cuestionario publicado para periodos futuros.", "success")
        if action == "archive" and version:
            version.estado = "archivado"
            db.session.commit()
            log_activity("archive_questionnaire", entity_type="cuestionario", entity_id=version.id)
            flash("Cuestionario archivado.", "success")
        return redirect(url_for("admin.questionnaires"))

    versions = CuestionarioVersion.query.order_by(CuestionarioVersion.created_at.desc()).all()
    implementation_evaluations = (
        Evaluacion.query.join(PeriodoEvaluacion)
        .filter(Evaluacion.estado.in_(REPORTABLE_EVALUATION_STATES))
        .filter(PeriodoEvaluacion.estado.in_(["borrador", "abierto", "reabierto", "cerrado"]))
        .order_by(PeriodoEvaluacion.created_at.desc(), Evaluacion.updated_at.desc())
        .limit(10)
        .all()
    )
    implementation_cards = [
        {"evaluacion": evaluation, "summary": summarize_evaluation(evaluation)}
        for evaluation in implementation_evaluations
    ]
    log_activity("view_questionnaires")
    return render_template(
        "admin/questionnaires.html",
        versions=versions,
        implementation_cards=implementation_cards,
    )


@bp.route("/cuestionarios/<int:version_id>/editar", methods=["GET", "POST"])
@role_required("administrador")
def edit_questionnaire(version_id: int):
    version = CuestionarioVersion.query.get_or_404(version_id)
    if request.method == "POST":
        if version.estado != "borrador":
            flash("Solo los borradores pueden modificarse.", "error")
            return redirect(url_for("admin.edit_questionnaire", version_id=version.id))

        add_reactive_axis = request.form.get("add_reactivo_eje")
        delete_reactive_id = request.form.get("delete_reactivo_id")
        if add_reactive_axis:
            axis = next(axis for axis in version.ejes if axis.id == int(add_reactive_axis))
            next_order = len(axis.reactivos) + 1
            db.session.add(
                ReactivoVersion(
                    eje_version=axis,
                    codigo=f"{axis.orden}.{next_order}",
                    orden=next_order,
                    pregunta="Nuevo reactivo",
                    opciones={
                        "0": "No implementado",
                        "1": "Incipiente",
                        "2": "En desarrollo",
                        "3": "Consolidado",
                    },
                )
            )
            db.session.commit()
            log_activity("add_reactive", entity_type="cuestionario", entity_id=version.id, metadata={"eje_id": axis.id})
            flash("Reactivo agregado al borrador.", "success")
        elif delete_reactive_id:
            reactive = ReactivoVersion.query.get_or_404(int(delete_reactive_id))
            if reactive.eje_version.cuestionario_version_id != version.id:
                flash("Reactivo inválido.", "error")
            else:
                axis = reactive.eje_version
                db.session.delete(reactive)
                db.session.flush()
                for index, item in enumerate(sorted(axis.reactivos, key=lambda value: value.orden), start=1):
                    item.orden = index
                    item.codigo = f"{axis.orden}.{index}"
                db.session.commit()
                log_activity("delete_reactive", entity_type="cuestionario", entity_id=version.id, metadata={"eje_id": axis.id})
                flash("Reactivo eliminado.", "success")
        else:
            version.nombre = request.form.get("nombre", version.nombre).strip()
            version.descripcion = request.form.get("descripcion", version.descripcion)
            for axis in version.ejes:
                axis.nombre = request.form.get(f"eje_nombre_{axis.id}", axis.nombre).strip()
                axis.descripcion = request.form.get(f"eje_desc_{axis.id}", axis.descripcion)
                axis.ponderacion = float(request.form.get(f"eje_pond_{axis.id}", axis.ponderacion))
                for reactive in axis.reactivos:
                    reactive.pregunta = request.form.get(
                        f"pregunta_{reactive.id}",
                        reactive.pregunta,
                    ).strip()
                    reactive.opciones = {
                        str(index): request.form.get(f"op_{reactive.id}_{index}", reactive.opciones[str(index)]).strip()
                        for index in range(4)
                    }
            db.session.commit()
            log_activity("update_questionnaire", entity_type="cuestionario", entity_id=version.id)
            flash("Cuestionario actualizado.", "success")
        return redirect(url_for("admin.edit_questionnaire", version_id=version.id))

    log_activity("view_questionnaire_editor", entity_type="cuestionario", entity_id=version.id)
    return render_template("admin/questionnaire_edit.html", version=version)


@bp.route("/cuestionarios/<int:version_id>/vista-llenado")
@role_required("administrador")
def questionnaire_fill_preview(version_id: int):
    version = CuestionarioVersion.query.get_or_404(version_id)
    total_questions = sum(len(axis.reactivos) for axis in version.ejes)
    log_activity("view_questionnaire_fill_preview", entity_type="cuestionario", entity_id=version.id)
    return render_template(
        "admin/questionnaire_fill_preview.html",
        version=version,
        total_questions=total_questions,
    )


@bp.route("/periodos", methods=["GET", "POST"])
@role_required("administrador")
def periods():
    if request.method == "POST":
        flash(
            "El flujo historico por periodos quedo archivado en modo de solo lectura. Usa Campanas para nuevos despliegues.",
            "error",
        )
        return redirect(url_for("admin.periods"))

    periods = PeriodoEvaluacion.query.order_by(PeriodoEvaluacion.created_at.desc()).all()
    versions = CuestionarioVersion.query.filter_by(estado="publicado").order_by(CuestionarioVersion.created_at.desc()).all()
    log_activity("view_periods")
    return render_template("admin/periods.html", periodos=periods, versiones=versions)


@bp.route("/evaluaciones/<int:evaluation_id>", methods=["GET", "POST"])
@role_required("administrador")
def evaluation_detail(evaluation_id: int):
    evaluation = Evaluacion.query.get_or_404(evaluation_id)
    if request.method == "POST":
        flash(
            "La gestion del flujo legado quedo archivada en modo de solo lectura. Usa Campanas y Asignaciones para nuevas operaciones.",
            "error",
        )
        return redirect(url_for("admin.evaluation_detail", evaluation_id=evaluation.id))

    summary = summarize_evaluation(evaluation)
    reviewers = Usuario.query.filter_by(rol="revisor", activo=True).order_by(Usuario.nombre).all()
    evaluators = Usuario.query.filter_by(rol="evaluador", activo=True).order_by(Usuario.nombre).all()
    log_activity("view_admin_evaluation", entity_type="evaluacion", entity_id=evaluation.id)
    return render_template(
        "admin/evaluation_detail.html",
        evaluacion=evaluation,
        summary=summary,
        revisores=reviewers,
        evaluadores=evaluators,
    )


@bp.route("/evaluaciones/<int:evaluation_id>/preview")
@role_required("administrador")
def evaluation_preview(evaluation_id: int):
    evaluation = Evaluacion.query.get_or_404(evaluation_id)
    questionnaire = evaluation.periodo.cuestionario_version
    response_map = {response.reactivo_version_id: response for response in evaluation.respuestas}
    summary = summarize_evaluation(evaluation)
    log_activity("view_implementation_preview", entity_type="evaluacion", entity_id=evaluation.id)
    return render_template(
        "admin/questionnaire_preview.html",
        evaluacion=evaluation,
        cuestionario=questionnaire,
        respuestas=response_map,
        summary=summary,
    )


@bp.route("/vista-capturista")
@role_required("administrador")
def evaluator_views():
    selected_period_id = request.args.get("periodo_id", type=int)
    selected_dependency_id = request.args.get("dependencia_id", type=int)
    selected_state = request.args.get("estado", type=str)

    query = (
        Evaluacion.query.join(PeriodoEvaluacion)
        .filter(Evaluacion.estado.in_(REPORTABLE_EVALUATION_STATES))
        .filter(PeriodoEvaluacion.estado.in_(["borrador", "abierto", "reabierto"]))
        .order_by(Evaluacion.updated_at.desc())
    )
    if selected_period_id:
        query = query.filter(Evaluacion.periodo_id == selected_period_id)
    if selected_dependency_id:
        query = query.filter(Evaluacion.dependencia_id == selected_dependency_id)
    if selected_state in REPORTABLE_EVALUATION_STATES:
        query = query.filter(Evaluacion.estado == selected_state)

    evaluations = query.all()
    cards = [{"evaluacion": evaluation, "summary": summarize_evaluation(evaluation)} for evaluation in evaluations]
    log_activity("view_evaluator_views")
    return render_template(
        "admin/evaluator_views.html",
        cards=cards,
        periodos=PeriodoEvaluacion.query.order_by(PeriodoEvaluacion.created_at.desc()).all(),
        dependencias=Dependencia.query.order_by(Dependencia.nombre).all(),
        reportable_states=sorted(REPORTABLE_EVALUATION_STATES),
        selected_period_id=selected_period_id,
        selected_dependency_id=selected_dependency_id,
        selected_state=selected_state,
    )


@bp.route("/evaluaciones/<int:evaluation_id>/vista-capturista")
@role_required("administrador")
def evaluator_view(evaluation_id: int):
    evaluation = db.session.get(Evaluacion, evaluation_id)
    if evaluation is None:
        flash("La evaluación solicitada no existe todavía. Primero crea un periodo para generar evaluaciones.", "error")
        return redirect(url_for("admin.evaluator_views"))
    from municipal_diagnostico.blueprints.evaluation import render_capture_screen

    log_activity("view_as_evaluator", entity_type="evaluacion", entity_id=evaluation.id)
    return render_capture_screen(
        evaluation,
        can_edit=False,
        preview_mode=True,
        admin_preview=True,
    )


@bp.route("/monitoreo")
@role_required("administrador")
def monitoring():
    selected_user_id = request.args.get("usuario_id", type=int)
    selected_role = request.args.get("rol", type=str)
    selected_dependency_id = request.args.get("dependencia_id", type=int)
    selected_type = request.args.get("tipo", type=str)
    from_date = request.args.get("fecha_desde", type=str)
    to_date = request.args.get("fecha_hasta", type=str)

    sessions_query = SesionPlataforma.query.join(Usuario).order_by(SesionPlataforma.ultima_actividad_at.desc())
    activities_query = ActividadPlataforma.query.outerjoin(Usuario).order_by(ActividadPlataforma.created_at.desc())

    if selected_user_id:
        sessions_query = sessions_query.filter(SesionPlataforma.usuario_id == selected_user_id)
        activities_query = activities_query.filter(ActividadPlataforma.usuario_id == selected_user_id)
    if selected_role:
        sessions_query = sessions_query.filter(Usuario.rol == selected_role)
        activities_query = activities_query.filter(Usuario.rol == selected_role)
    if selected_dependency_id:
        sessions_query = sessions_query.filter(Usuario.dependencia_id == selected_dependency_id)
        activities_query = activities_query.filter(Usuario.dependencia_id == selected_dependency_id)
    if selected_type:
        activities_query = activities_query.filter(ActividadPlataforma.tipo == selected_type)
    if from_date:
        from_value = to_utc_naive(
            datetime.combine(datetime.strptime(from_date, "%Y-%m-%d").date(), time.min),
            assume_local=True,
        )
        sessions_query = sessions_query.filter(SesionPlataforma.ultima_actividad_at >= from_value)
        activities_query = activities_query.filter(ActividadPlataforma.created_at >= from_value)
    if to_date:
        to_value = to_utc_naive(
            datetime.combine(datetime.strptime(to_date, "%Y-%m-%d").date(), time.max),
            assume_local=True,
        )
        sessions_query = sessions_query.filter(SesionPlataforma.ultima_actividad_at <= to_value)
        activities_query = activities_query.filter(ActividadPlataforma.created_at <= to_value)

    sessions = sessions_query.limit(25).all()
    activities = activities_query.limit(100).all()
    type_counts = Counter(activity.tipo for activity in activities)
    session_counts_by_user = Counter(session.usuario_id for session in sessions if session.usuario_id)
    user_activity_map = {}
    for activity in activities:
        user_key = activity.usuario_id or 0
        if user_key not in user_activity_map:
            user_activity_map[user_key] = {
                "usuario": activity.usuario,
                "nombre": activity.usuario.nombre if activity.usuario else "Sistema",
                "rol": activity.usuario.nombre_rol if activity.usuario else "Sistema",
                "dependencia": activity.usuario.dependencia.nombre if activity.usuario and activity.usuario.dependencia else "Sin dependencia",
                "acciones": 0,
                "sesiones": session_counts_by_user.get(activity.usuario_id, 0),
                "ultima_actividad": activity.created_at,
                "tipos": Counter(),
            }
        row = user_activity_map[user_key]
        row["acciones"] += 1
        row["tipos"][activity_label(activity.tipo)] += 1
        if activity.created_at and activity.created_at > row["ultima_actividad"]:
            row["ultima_actividad"] = activity.created_at

    user_activity_rows = sorted(
        [
            {
                **row,
                "accion_principal": row["tipos"].most_common(1)[0][0] if row["tipos"] else "Sin acciones",
                "accion_principal_total": row["tipos"].most_common(1)[0][1] if row["tipos"] else 0,
            }
            for row in user_activity_map.values()
        ],
        key=lambda item: (item["acciones"], item["nombre"]),
        reverse=True,
    )
    summary = {
        "active_sessions": SesionPlataforma.query.filter_by(activa=True).count(),
        "recent_sessions": len(sessions),
        "events": len(activities),
        "unique_users": len({activity.usuario_id for activity in activities if activity.usuario_id}),
        "top_types": [(activity_label(item[0]), item[1]) for item in type_counts.most_common(8)],
    }
    log_activity("view_monitoring")
    return render_template(
        "admin/monitoring.html",
        sessions=sessions,
        activities=activities,
        user_activity_rows=user_activity_rows,
        summary=summary,
        usuarios=Usuario.query.order_by(Usuario.nombre).all(),
        dependencias=Dependencia.query.order_by(Dependencia.nombre).all(),
        selected_user_id=selected_user_id,
        selected_role=selected_role,
        selected_dependency_id=selected_dependency_id,
        selected_type=selected_type,
        from_date=from_date,
        to_date=to_date,
        activity_types=[
            {"value": item, "label": activity_label(item)}
            for item in sorted({row[0] for row in db.session.query(ActividadPlataforma.tipo).distinct().all() if row[0]})
        ],
        activity_label=activity_label,
    )


def clean_catalog_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def dependency_name_exists(name: str, current_id: int | None = None) -> bool:
    query = Dependencia.query.filter_by(nombre=name)
    if current_id:
        query = query.filter(Dependencia.id != current_id)
    return db.session.query(query.exists()).scalar()


def area_name_exists(dependency_id: int, name: str, current_id: int | None = None) -> bool:
    query = Area.query.filter_by(dependencia_id=dependency_id, nombre=name)
    if current_id:
        query = query.filter(Area.id != current_id)
    return db.session.query(query.exists()).scalar()


def user_email_exists(email: str, current_user_id: int | None = None) -> bool:
    query = Usuario.query.filter_by(correo=email)
    if current_user_id:
        query = query.filter(Usuario.id != current_user_id)
    return db.session.query(query.exists()).scalar()


def validate_user_payload(form_data, *, current_user_id: int | None = None, password_required: bool = True):
    nombre = clean_catalog_text(form_data.get("nombre"))
    correo = clean_catalog_text(form_data.get("correo"))
    password = clean_catalog_text(form_data.get("password"))
    rol = clean_catalog_text(form_data.get("rol"))
    dependencia_id = form_data.get("dependencia_id", type=int)
    area_id = form_data.get("area_id", type=int)

    if not nombre:
        return None, "Captura el nombre del usuario."
    if not correo:
        return None, "Captura el correo del usuario."
    correo = correo.lower()
    if user_email_exists(correo, current_user_id=current_user_id):
        return None, "Ya existe un usuario con ese correo."
    if rol not in ROLE_DEFINITIONS:
        return None, "Selecciona un rol válido."
    if password_required and not password:
        return None, "Captura una contraseña inicial para el usuario."

    dependency = db.session.get(Dependencia, dependencia_id) if dependencia_id else None
    area = db.session.get(Area, area_id) if area_id else None

    if area and not area.activa:
        return None, "La unidad administrativa seleccionada está inactiva."
    if dependency and not dependency.activa:
        return None, "La dependencia seleccionada está inactiva."
    if area and not dependency:
        return None, "Primero selecciona una dependencia para asociar una unidad administrativa."
    if area and dependency and area.dependencia_id != dependency.id:
        return None, "La unidad administrativa seleccionada no pertenece a la dependencia indicada."

    return {
        "nombre": nombre,
        "correo": correo,
        "password": password,
        "rol": rol,
        "dependencia_id": dependency.id if dependency else None,
        "area_id": area.id if area else None,
    }, None


def dependency_delete_blockers(dependency: Dependencia) -> list[str]:
    blockers = []
    if dependency.evaluaciones:
        blockers.append("tiene evaluaciones vinculadas")
    if dependency.areas:
        blockers.append("tiene unidades administrativas registradas")
    if dependency.usuarios:
        blockers.append("tiene usuarios asociados")
    return blockers


def area_has_operational_data(area: Area) -> bool:
    return any(
        [
            bool(area.usuarios),
            bool(area.asignaciones),
            bool(area.respuestas),
            EvidenciaEje.query.filter_by(area_id=area.id).first() is not None,
            ComentarioEje.query.filter_by(area_id=area.id).first() is not None,
        ]
    )


def area_delete_blockers(area: Area) -> list[str]:
    blockers = []
    if area.usuarios:
        blockers.append("tiene usuarios asociados")
    if area.asignaciones:
        blockers.append("tiene asignaciones de captura")
    if area.respuestas:
        blockers.append("tiene respuestas registradas")
    if EvidenciaEje.query.filter_by(area_id=area.id).first() is not None:
        blockers.append("tiene evidencias documentales")
    if ComentarioEje.query.filter_by(area_id=area.id).first() is not None:
        blockers.append("tiene comentarios de módulo")
    return blockers


def would_remove_last_active_admin(
    user: Usuario,
    *,
    next_role: str | None = None,
    next_active: bool | None = None,
    deleting: bool = False,
) -> bool:
    current_is_active_admin = user.rol == "administrador" and user.activo
    active_admins = Usuario.query.filter_by(rol="administrador", activo=True).count()
    if not current_is_active_admin:
        return False
    if deleting:
        return active_admins <= 1
    resulting_role = next_role if next_role is not None else user.rol
    resulting_active = next_active if next_active is not None else user.activo
    if resulting_role == "administrador" and resulting_active:
        return False
    return active_admins <= 1


def user_delete_blockers(user: Usuario) -> list[str]:
    blockers = []
    if user.cuestionarios_creados:
        blockers.append("ha creado cuestionarios")
    if user.periodos_creados:
        blockers.append("ha creado periodos")
    if user.evaluaciones_revisadas:
        blockers.append("está asignado como revisor")
    if user.respuestas_capturadas:
        blockers.append("tiene respuestas capturadas")
    if user.evidencias_subidas:
        blockers.append("tiene evidencias cargadas")
    if user.observaciones:
        blockers.append("tiene observaciones de revisión")
    if user.comentarios_eje:
        blockers.append("tiene comentarios de módulo")
    if user.asignaciones:
        blockers.append("tiene asignaciones activas")
    if user.sesiones or user.actividades:
        blockers.append("tiene bitácora de uso")
    if Notificacion.query.filter_by(usuario_id=user.id).first() is not None:
        blockers.append("tiene notificaciones asociadas")
    return blockers


def notify_assigned_users(evaluation: Evaluacion, tipo: str, mensaje: str, enlace: str) -> None:
    recipients = [assignment.usuario for assignment in evaluation.asignaciones if assignment.tipo == "captura"]
    if not recipients:
        recipients = Usuario.query.filter_by(
            dependencia_id=evaluation.dependencia_id,
            rol="evaluador",
            activo=True,
        ).all()
    for recipient in recipients:
        notify_user(recipient, tipo, mensaje, enlace)


def activity_label(activity_type: str) -> str:
    return ACTIVITY_LABELS.get(activity_type, activity_type.replace("_", " ").capitalize())
