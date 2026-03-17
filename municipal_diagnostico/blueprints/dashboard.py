from flask import Blueprint, jsonify, redirect, render_template, url_for
from flask_login import current_user, login_required

from municipal_diagnostico.decorators import role_required
from municipal_diagnostico.extensions import db
from municipal_diagnostico.models import AsignacionCuestionario, CampanaCuestionario, Evaluacion, Notificacion, PeriodoEvaluacion
from municipal_diagnostico.services.activity_logger import log_activity, touch_platform_session
from municipal_diagnostico.services.campaign_analytics import FINAL_ASSIGNMENT_STATES, summarize_assignment, summarize_campaign
from municipal_diagnostico.services.analytics import REPORTABLE_EVALUATION_STATES, summarize_evaluation, summarize_period
from municipal_diagnostico.timeutils import to_localtime


bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


@bp.route("/")
@login_required
def home():
    log_activity("view_dashboard", metadata={"rol": current_user.rol})
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


def build_admin_dashboard() -> dict:
    campaigns = CampanaCuestionario.query.order_by(CampanaCuestionario.created_at.desc()).all()
    active_campaign = next((campaign for campaign in campaigns if campaign.estado == "activa"), None)
    selected_campaign = active_campaign or (campaigns[0] if campaigns else None)
    summary = summarize_campaign(selected_campaign, role="administrador") if selected_campaign else {
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
    return {
        "campaigns": campaigns[:5],
        "selected_campaign": selected_campaign,
        "summary": summary,
        "focus_assignments": focus_assignments,
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
