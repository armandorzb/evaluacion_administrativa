from __future__ import annotations

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, url_for
from flask_login import current_user, login_required, logout_user

from municipal_diagnostico.extensions import db
from municipal_diagnostico.models import AsignacionCuestionario, CampanaCuestionario, Evaluacion, Notificacion
from municipal_diagnostico.services.activity_logger import close_platform_session, log_activity, touch_platform_session
from municipal_diagnostico.services.analytics import REPORTABLE_EVALUATION_STATES, summarize_evaluation
from municipal_diagnostico.services.campaign_analytics import FINAL_ASSIGNMENT_STATES, summarize_assignment, summarize_campaign
from municipal_diagnostico.services.module_access import (
    MODULE_BIENESTAR,
    MODULE_DIAGNOSTICO,
    endpoint_for_module,
    landing_endpoint_for_user,
)
from municipal_diagnostico.timeutils import to_localtime


bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


@bp.route("/")
@login_required
def home():
    target_endpoint = landing_endpoint_for_user(current_user)
    if target_endpoint is None:
        return reject_user_without_modules()
    return redirect(url_for(target_endpoint))


@bp.route("/modulos")
@login_required
def modules():
    target_endpoint = landing_endpoint_for_user(current_user)
    if target_endpoint is None:
        return reject_user_without_modules()
    if target_endpoint != "dashboard.modules":
        return redirect(url_for(target_endpoint))

    log_activity(
        "view_module_selector",
        metadata={"modulos": current_user.modulos_disponibles, "rol": current_user.rol},
    )
    return render_template(
        "dashboard/modules.html",
        modules=[
            {
                "slug": MODULE_DIAGNOSTICO,
                "title": "Diagnóstico Integral Municipal",
                "subtitle": "Cuestionarios, campañas, asignaciones y reportería operativa",
                "description": "Mantiene la arquitectura actual del sistema para operación institucional, seguimiento y reportes ejecutivos.",
                "url": url_for("dashboard.open_module", module_slug=MODULE_DIAGNOSTICO),
                "is_available": current_user.puede_acceder_diagnostico,
            },
            {
                "slug": MODULE_BIENESTAR,
                "title": "Bienestar Policial",
                "subtitle": "Encuesta pública, tablero propio y exportaciones ejecutivas",
                "description": "Opera como módulo independiente con identidad visual propia, captura anónima y panel interno especializado.",
                "url": url_for("dashboard.open_module", module_slug=MODULE_BIENESTAR),
                "is_available": current_user.puede_acceder_bienestar,
            },
        ],
    )


@bp.route("/modulos/<string:module_slug>")
@login_required
def open_module(module_slug: str):
    target_endpoint = endpoint_for_module(current_user, module_slug)
    if target_endpoint is None:
        log_activity(
            "module_access_denied",
            metadata={"modulo": module_slug, "rol": current_user.rol},
        )
        abort(403, description="No cuentas con acceso al módulo solicitado.")

    log_activity(
        "select_module",
        metadata={"modulo": module_slug, "rol": current_user.rol},
    )
    return redirect(url_for(target_endpoint))


@bp.route("/diagnostico")
@login_required
def diagnostic_home():
    if not current_user.puede_acceder_diagnostico:
        log_activity(
            "module_access_denied",
            metadata={"modulo": MODULE_DIAGNOSTICO, "rol": current_user.rol},
        )
        abort(403, description="No cuentas con acceso al módulo Diagnóstico Integral Municipal.")

    log_activity(
        "view_dashboard",
        metadata={"rol": current_user.rol, "modulo": MODULE_DIAGNOSTICO},
    )
    if current_user.rol == "administrador":
        return render_template("dashboard/admin.html", **build_admin_dashboard())
    if current_user.rol == "revisor":
        return render_template("dashboard/revisor.html", **build_reviewer_dashboard())
    if current_user.rol == "consulta":
        return render_template("dashboard/consulta.html", **build_consultation_dashboard())
    return render_template("dashboard/evaluador.html", **build_evaluator_dashboard())


@bp.route("/notificaciones/<int:notification_id>/leer")
@login_required
def read_notification(notification_id: int):
    notification = Notificacion.query.get_or_404(notification_id)
    if notification.usuario_id != current_user.id:
        return redirect(url_for("dashboard.home"))
    notification.leida = True
    db.session.commit()
    log_activity(
        "read_notification",
        entity_type="notificacion",
        entity_id=notification.id,
        metadata={"tipo": notification.tipo},
    )
    if notification.enlace:
        return redirect(notification.enlace)
    return redirect(url_for("dashboard.home"))


@bp.route("/heartbeat", methods=["POST"])
@login_required
def heartbeat():
    session_record = touch_platform_session(commit=True)
    local_value = to_localtime(session_record.ultima_actividad_at if session_record else None)
    return jsonify(
        {
            "ok": True,
            "last_seen": local_value.strftime("%d/%m/%Y %H:%M") if local_value else None,
        }
    )


def reject_user_without_modules():
    log_activity(
        "login_denied_no_modules",
        metadata={"rol": getattr(current_user, "rol", None)},
        commit=False,
    )
    close_platform_session()
    db.session.commit()
    logout_user()
    flash("Tu cuenta no tiene módulos asignados. Solicita acceso a un administrador.", "error")
    return redirect(url_for("auth.login"))


def build_admin_dashboard() -> dict:
    campaigns = CampanaCuestionario.query.order_by(CampanaCuestionario.created_at.desc()).all()
    active_campaign = next((campaign for campaign in campaigns if campaign.estado == "activa"), None)
    selected_campaign = active_campaign or (campaigns[0] if campaigns else None)
    recent_evaluations = (
        Evaluacion.query.filter(Evaluacion.estado.in_(REPORTABLE_EVALUATION_STATES))
        .order_by(Evaluacion.updated_at.desc())
        .limit(4)
        .all()
    )
    campaign_summary = summarize_campaign(selected_campaign, role="administrador") if selected_campaign else {
        "rows": [],
        "visible_total": 0,
        "avg_completion": 0,
        "completed_count": 0,
        "total_assignments": 0,
    }
    focus_assignments = []
    if selected_campaign:
        ordered = sorted(selected_campaign.asignaciones, key=lambda item: item.updated_at, reverse=True)
        for assignment in ordered[:6]:
            focus_assignments.append({"asignacion": assignment, "summary": summarize_assignment(assignment)})

    report_exports = []
    for evaluation in recent_evaluations:
        evaluation_summary = summarize_evaluation(evaluation)
        report_exports.append(
            {
                "title": evaluation.dependencia.nombre,
                "subtitle": evaluation.periodo.nombre,
                "state_label": evaluation_summary["state_label"],
                "level_slug": evaluation_summary["level_slug"],
                "index_score": evaluation_summary["index_score"],
                "completion": evaluation_summary["completion"],
                "report_url": url_for("reports.evaluation_report", evaluation_id=evaluation.id),
                "pdf_url": url_for("reports.evaluation_pdf", evaluation_id=evaluation.id),
                "xlsx_url": url_for("reports.evaluation_excel", evaluation_id=evaluation.id),
                "word_url": url_for("reports.evaluation_word", evaluation_id=evaluation.id),
            }
        )

    if not report_exports:
        recent_assignments = AsignacionCuestionario.query.order_by(AsignacionCuestionario.updated_at.desc()).limit(4).all()
        for assignment in recent_assignments:
            assignment_summary = summarize_assignment(assignment)
            report_exports.append(
                {
                    "title": assignment.objetivo_nombre,
                    "subtitle": assignment.campana.nombre,
                    "state_label": assignment_summary["state_label"],
                    "level_slug": assignment_summary["level_slug"],
                    "index_score": assignment_summary["index_score"],
                    "completion": assignment_summary["completion"],
                    "report_url": url_for("campaigns.assignment_report", assignment_id=assignment.id),
                    "pdf_url": url_for("campaigns.assignment_pdf", assignment_id=assignment.id),
                    "xlsx_url": url_for("campaigns.assignment_excel", assignment_id=assignment.id),
                    "word_url": url_for("campaigns.assignment_word", assignment_id=assignment.id),
                }
            )

    return {
        "campaigns": campaigns[:5],
        "selected_campaign": selected_campaign,
        "summary": campaign_summary,
        "focus_assignments": focus_assignments,
        "report_exports": report_exports,
        "counts": {
            "campanas": len(campaigns),
            "asignaciones": AsignacionCuestionario.query.count(),
            "respondidas": AsignacionCuestionario.query.filter(AsignacionCuestionario.estado.in_(FINAL_ASSIGNMENT_STATES)).count(),
            "activas": len([campaign for campaign in campaigns if campaign.estado == "activa"]),
        },
    }


def build_evaluator_dashboard() -> dict:
    assignments = (
        AsignacionCuestionario.query.filter(
            (AsignacionCuestionario.respondente_id == current_user.id)
            | (AsignacionCuestionario.usuario_id == current_user.id)
        )
        .order_by(AsignacionCuestionario.updated_at.desc())
        .all()
    )
    cards = [{"asignacion": assignment, "summary": summarize_assignment(assignment)} for assignment in assignments]
    return {"cards": cards}


def build_reviewer_dashboard() -> dict:
    evaluations = (
        Evaluacion.query.filter_by(revisor_id=current_user.id)
        .order_by(Evaluacion.updated_at.desc())
        .all()
    )
    pending_review = [evaluation for evaluation in evaluations if evaluation.estado == "en_revision"]
    returned = [evaluation for evaluation in evaluations if evaluation.estado == "devuelta"]
    approved = [evaluation for evaluation in evaluations if evaluation.estado in {"aprobada", "cerrada"}]
    return {
        "pending_review": pending_review,
        "returned": returned,
        "approved": approved,
    }


def build_consultation_dashboard() -> dict:
    campaigns = (
        CampanaCuestionario.query.filter(CampanaCuestionario.estado.in_(["activa", "cerrada"]))
        .order_by(CampanaCuestionario.created_at.desc())
        .all()
    )
    selected_campaign = campaigns[0] if campaigns else None
    summary = summarize_campaign(selected_campaign, role="consulta") if selected_campaign else {"rows": [], "visible_total": 0}
    return {"selected_campaign": selected_campaign, "summary": summary}
