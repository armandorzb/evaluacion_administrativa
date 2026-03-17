from flask import Blueprint, abort, render_template, request, send_file
from flask_login import current_user

from municipal_diagnostico.blueprints.evaluation import user_can_view
from municipal_diagnostico.decorators import role_required
from municipal_diagnostico.models import Dependencia, Evaluacion, PeriodoEvaluacion
from municipal_diagnostico.services.activity_logger import log_activity
from municipal_diagnostico.services.analytics import (
    OFFICIAL_EVALUATION_STATES,
    REPORTABLE_EVALUATION_STATES,
    historical_series,
    select_reporting_period,
    summarize_axis_for_period,
    summarize_evaluation,
    summarize_period,
    summarize_period_executive,
    visible_states_for_role,
)
from municipal_diagnostico.services.exports import (
    build_evaluation_pdf,
    build_period_csv,
    build_period_excel,
)


bp = Blueprint("reports", __name__, url_prefix="/reportes")


@bp.route("/ejecutivo")
@role_required("administrador", "consulta")
def executive_home():
    selected_period_id = request.args.get("periodo_id", type=int)
    periods = PeriodoEvaluacion.query.order_by(PeriodoEvaluacion.created_at.desc()).all()
    selected_period = select_reporting_period(periods, selected_period_id)
    visible_states = visible_states_for_role(current_user.rol)
    executive_summary = (
        summarize_period_executive(selected_period, include_states=visible_states)
        if selected_period
        else {
            "dependency_cards": [],
            "axis_cards": [],
            "visible_states": sorted(visible_states),
            "total_dependencies": 0,
            "total_axes": 0,
            "official_count": 0,
            "preliminary_count": 0,
        }
    )
    log_activity("view_executive_home", entity_type="periodo", entity_id=selected_period.id if selected_period else None)

    return render_template(
        "reports/executive_home.html",
        periodos=periods,
        selected_period=selected_period,
        selected_period_id=selected_period.id if selected_period else None,
        executive_summary=executive_summary,
    )


@bp.route("/ejecutivo/dependencias/<int:dependency_id>")
@role_required("administrador", "consulta")
def executive_dependency(dependency_id: int):
    selected_period_id = request.args.get("periodo_id", type=int)
    periods = PeriodoEvaluacion.query.order_by(PeriodoEvaluacion.created_at.desc()).all()
    selected_period = select_reporting_period(periods, selected_period_id)
    if selected_period is None:
        abort(404)

    visible_states = visible_states_for_role(current_user.rol)
    executive_summary = summarize_period_executive(selected_period, include_states=visible_states)
    dependency_card = next(
        (
            card
            for card in executive_summary["dependency_cards"]
            if card["dependency_id"] == dependency_id
        ),
        None,
    )
    if dependency_card is None:
        abort(404)

    evaluation = dependency_card["evaluacion"]
    history = historical_series(
        Evaluacion.query.filter_by(dependencia_id=evaluation.dependencia_id)
        .order_by(Evaluacion.created_at.asc())
        .all()
    )
    log_activity("view_executive_dependency", entity_type="evaluacion", entity_id=evaluation.id)

    return render_template(
        "reports/executive_dependency.html",
        evaluacion=evaluation,
        summary=dependency_card["summary"],
        history=history,
        periodos=periods,
        selected_period=selected_period,
        dependency_card=dependency_card,
        peer_cards=executive_summary["dependency_cards"][:8],
    )


@bp.route("/ejecutivo/ejes/<int:axis_id>")
@role_required("administrador", "consulta")
def executive_axis(axis_id: int):
    selected_period_id = request.args.get("periodo_id", type=int)
    periods = PeriodoEvaluacion.query.order_by(PeriodoEvaluacion.created_at.desc()).all()
    selected_period = select_reporting_period(periods, selected_period_id)
    if selected_period is None:
        abort(404)

    visible_states = visible_states_for_role(current_user.rol)
    axis_summary = summarize_axis_for_period(selected_period, axis_id, include_states=visible_states)
    if axis_summary is None:
        abort(404)
    log_activity("view_executive_axis", entity_type="eje", entity_id=axis_id, metadata={"periodo_id": selected_period.id})

    return render_template(
        "reports/executive_axis.html",
        periodos=periods,
        selected_period=selected_period,
        axis_summary=axis_summary,
    )


@bp.route("/")
@role_required("administrador")
def index():
    selected_period_id = request.args.get("periodo_id", type=int)
    selected_dependencia_id = request.args.get("dependencia_id", type=int)
    selected_state = request.args.get("estado", type=str)

    periods = PeriodoEvaluacion.query.order_by(PeriodoEvaluacion.created_at.desc()).all()
    dependencias = Dependencia.query.order_by(Dependencia.nombre).all()
    selected_period = select_reporting_period(periods, selected_period_id)

    query = Evaluacion.query.order_by(Evaluacion.updated_at.desc())
    if selected_period_id:
        query = query.filter_by(periodo_id=selected_period_id)
    if selected_dependencia_id:
        query = query.filter_by(dependencia_id=selected_dependencia_id)
    if selected_state in REPORTABLE_EVALUATION_STATES:
        query = query.filter_by(estado=selected_state)

    evaluations = query.all()
    cards = [{"evaluacion": evaluation, "summary": summarize_evaluation(evaluation)} for evaluation in evaluations]
    period_summary = (
        summarize_period(selected_period, include_states=REPORTABLE_EVALUATION_STATES)
        if selected_period
        else None
    )
    log_activity("view_reports_hub", entity_type="periodo", entity_id=selected_period.id if selected_period else None)

    return render_template(
        "reports/index.html",
        cards=cards,
        periodos=periods,
        dependencias=dependencias,
        selected_period=selected_period,
        selected_period_id=selected_period.id if selected_period else None,
        selected_dependencia_id=selected_dependencia_id,
        selected_state=selected_state,
        period_summary=period_summary,
        reportable_states=sorted(REPORTABLE_EVALUATION_STATES),
    )


@bp.route("/evaluaciones/<int:evaluation_id>")
@role_required("administrador", "revisor", "evaluador", "consulta")
def evaluation_report(evaluation_id: int):
    evaluation = Evaluacion.query.get_or_404(evaluation_id)
    if not user_can_view(evaluation):
        abort(403)
    if current_user.rol == "evaluador" and evaluation.estado not in {"en_revision", "aprobada", "cerrada"}:
        abort(403)

    summary = summarize_evaluation(evaluation)
    history = historical_series(
        Evaluacion.query.filter_by(dependencia_id=evaluation.dependencia_id)
        .order_by(Evaluacion.created_at.asc())
        .all()
    )
    log_activity("view_evaluation_report", entity_type="evaluacion", entity_id=evaluation.id)
    return render_template(
        "reports/evaluation_report.html",
        evaluacion=evaluation,
        summary=summary,
        history=history,
    )


@bp.route("/evaluaciones/<int:evaluation_id>/pdf")
@role_required("administrador", "revisor", "evaluador", "consulta")
def evaluation_pdf(evaluation_id: int):
    evaluation = Evaluacion.query.get_or_404(evaluation_id)
    if not user_can_view(evaluation):
        abort(403)
    if current_user.rol == "evaluador" and evaluation.estado not in {"en_revision", "aprobada", "cerrada"}:
        abort(403)
    buffer = build_evaluation_pdf(evaluation)
    log_activity("export_pdf", entity_type="evaluacion", entity_id=evaluation.id)
    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"reporte-{evaluation.dependencia.nombre}-{evaluation.periodo.nombre}.pdf",
    )


@bp.route("/periodos/<int:period_id>/excel")
@role_required("administrador", "revisor", "consulta")
def period_excel(period_id: int):
    period = PeriodoEvaluacion.query.get_or_404(period_id)
    include_states = REPORTABLE_EVALUATION_STATES if current_user.rol == "administrador" else OFFICIAL_EVALUATION_STATES
    buffer = build_period_excel(period, include_states=include_states)
    log_activity("export_excel", entity_type="periodo", entity_id=period.id)
    return send_file(
        buffer,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"periodo-{period.nombre}.xlsx",
    )


@bp.route("/periodos/<int:period_id>/csv")
@role_required("administrador", "revisor", "consulta")
def period_csv(period_id: int):
    period = PeriodoEvaluacion.query.get_or_404(period_id)
    include_states = REPORTABLE_EVALUATION_STATES if current_user.rol == "administrador" else OFFICIAL_EVALUATION_STATES
    buffer = build_period_csv(period, include_states=include_states)
    log_activity("export_csv", entity_type="periodo", entity_id=period.id)
    return send_file(
        buffer,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"periodo-{period.nombre}.csv",
    )


@bp.route("/periodos/<int:period_id>")
@role_required("administrador", "revisor", "consulta")
def period_report(period_id: int):
    period = PeriodoEvaluacion.query.get_or_404(period_id)
    include_states = REPORTABLE_EVALUATION_STATES if current_user.rol == "administrador" else OFFICIAL_EVALUATION_STATES
    summary = summarize_period(period, include_states=include_states)
    log_activity("view_period_report", entity_type="periodo", entity_id=period.id)
    return render_template("reports/period_report.html", periodo=period, summary=summary)
