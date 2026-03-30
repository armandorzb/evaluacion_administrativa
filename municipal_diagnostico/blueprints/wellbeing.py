from __future__ import annotations

from uuid import uuid4

from flask import Blueprint, Response, abort, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user

from municipal_diagnostico.decorators import wellbeing_role_required
from municipal_diagnostico.extensions import db
from municipal_diagnostico.models import BienestarEncuesta, BienestarPregunta
from municipal_diagnostico.services.activity_logger import log_activity
from municipal_diagnostico.services.wellbeing import (
    build_wellbeing_csv,
    build_wellbeing_dashboard_summary,
    ensure_wellbeing_questions,
    list_active_questions,
    persist_wellbeing_progress,
    question_order_exists,
    serialize_question,
    validate_question_payload,
)
from municipal_diagnostico.services.wellbeing_exports import (
    build_wellbeing_excel,
    build_wellbeing_pdf,
    build_wellbeing_word,
)
from municipal_diagnostico.wellbeing_seed import DEFAULT_WELLBEING_STRATA


bp = Blueprint("wellbeing", __name__, url_prefix="/bienestar")


@bp.route("/")
def home():
    return render_public_home(public_mode=False)


@bp.route("/publico")
def public_entry():
    return render_public_home(public_mode=True)


def render_public_home(*, public_mode: bool):
    ensure_wellbeing_questions()
    return render_template(
        "bienestar/index.html",
        total_questions=len(list_active_questions()),
        estratos=DEFAULT_WELLBEING_STRATA,
        public_url=url_for("wellbeing.public_entry", _external=True),
        public_mode=public_mode,
    )


@bp.route("/encuesta")
def survey():
    ensure_wellbeing_questions()
    folio = (request.args.get("folio") or "").strip().upper()
    if not folio:
        flash("Primero inicia una encuesta para generar un folio anónimo.", "error")
        return redirect(url_for("wellbeing.home"))

    survey_record = BienestarEncuesta.query.filter_by(hash_id=folio).first()
    if survey_record is None:
        flash("No se encontró la encuesta solicitada.", "error")
        return redirect(url_for("wellbeing.home"))

    log_activity("view_wellbeing_survey", entity_type="bienestar_encuesta", entity_id=survey_record.id)
    return render_template(
        "bienestar/survey.html",
        folio=folio,
        total_questions=len(list_active_questions()),
        public_mode=not current_user.is_authenticated,
    )


@bp.route("/gracias")
def thanks():
    return render_template("bienestar/thanks.html", public_mode=not current_user.is_authenticated)


@bp.route("/panel")
@wellbeing_role_required("administrador", "consulta")
def dashboard():
    summary = build_wellbeing_dashboard_summary()
    log_activity("view_wellbeing_dashboard", metadata={"modulo": "bienestar"})
    public_url = url_for("wellbeing.public_entry", _external=True)
    return render_template("bienestar/dashboard.html", summary=summary, public_url=public_url)


@bp.route("/preguntas", methods=["GET", "POST"])
@wellbeing_role_required("administrador")
def questions():
    ensure_wellbeing_questions()

    if request.method == "POST":
        action = (request.form.get("action") or "").strip()

        if action == "add":
            payload, error = validate_question_payload(request.form)
            if error:
                flash(error, "error")
            elif question_order_exists(payload["orden"]):
                flash("Ya existe una pregunta con ese orden.", "error")
            else:
                question = BienestarPregunta(
                    orden=payload["orden"],
                    dimension=payload["dimension"],
                    texto=payload["texto"],
                    opciones=payload["opciones"],
                    activa=True,
                )
                db.session.add(question)
                db.session.commit()
                log_activity("create_wellbeing_question", entity_type="bienestar_pregunta", entity_id=question.id)
                flash("Pregunta creada.", "success")

        elif action == "update":
            question = db.session.get(BienestarPregunta, request.form.get("question_id", type=int))
            if question is None:
                flash("La pregunta solicitada no existe.", "error")
            else:
                payload, error = validate_question_payload(request.form)
                if error:
                    flash(error, "error")
                elif question_order_exists(payload["orden"], current_id=question.id):
                    flash("Ya existe otra pregunta con ese orden.", "error")
                else:
                    question.orden = payload["orden"]
                    question.dimension = payload["dimension"]
                    question.texto = payload["texto"]
                    question.opciones = payload["opciones"]
                    db.session.commit()
                    log_activity("update_wellbeing_question", entity_type="bienestar_pregunta", entity_id=question.id)
                    flash("Pregunta actualizada.", "success")

        elif action == "toggle":
            question = db.session.get(BienestarPregunta, request.form.get("question_id", type=int))
            if question is None:
                flash("La pregunta solicitada no existe.", "error")
            else:
                question.activa = not question.activa
                db.session.commit()
                log_activity(
                    "toggle_wellbeing_question",
                    entity_type="bienestar_pregunta",
                    entity_id=question.id,
                    metadata={"activa": question.activa},
                )
                flash("Pregunta activada." if question.activa else "Pregunta desactivada.", "success")

        elif action == "delete":
            question = db.session.get(BienestarPregunta, request.form.get("question_id", type=int))
            if question is None:
                flash("La pregunta solicitada no existe.", "error")
            elif question.respuestas:
                flash("No puedes eliminar una pregunta que ya tiene respuestas registradas.", "error")
            else:
                question_id = question.id
                db.session.delete(question)
                db.session.commit()
                log_activity("delete_wellbeing_question", entity_type="bienestar_pregunta", entity_id=question_id)
                flash("Pregunta eliminada.", "success")

        return redirect(url_for("wellbeing.questions"))

    questions_query = BienestarPregunta.query.order_by(BienestarPregunta.orden.asc()).all()
    log_activity("view_wellbeing_questions")
    return render_template(
        "bienestar/questions.html",
        questions=questions_query,
        active_count=len([question for question in questions_query if question.activa]),
        inactive_count=len([question for question in questions_query if not question.activa]),
        dimensions=sorted({question.dimension for question in questions_query}),
    )


@bp.route("/exportar/csv")
@wellbeing_role_required("administrador", "consulta")
def export_csv():
    payload = build_wellbeing_csv()
    log_activity("export_wellbeing_csv")
    return Response(
        payload,
        mimetype="text/csv",
        headers={"Content-Disposition": 'attachment; filename="bienestar.csv"'},
    )


@bp.route("/exportar/pdf")
@wellbeing_role_required("administrador", "consulta")
def export_pdf():
    buffer = build_wellbeing_pdf(public_url=url_for("wellbeing.public_entry", _external=True))
    log_activity("export_pdf", entity_type="bienestar")
    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="bienestar-institucional.pdf",
    )


@bp.route("/exportar/xlsx")
@wellbeing_role_required("administrador", "consulta")
def export_excel():
    buffer = build_wellbeing_excel(public_url=url_for("wellbeing.public_entry", _external=True))
    log_activity("export_excel", entity_type="bienestar")
    return send_file(
        buffer,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="bienestar-institucional.xlsx",
    )


@bp.route("/exportar/word")
@wellbeing_role_required("administrador", "consulta")
def export_word():
    buffer = build_wellbeing_word(public_url=url_for("wellbeing.public_entry", _external=True))
    log_activity("export_word", entity_type="bienestar")
    return send_file(
        buffer,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name="bienestar-institucional.docx",
    )


@bp.route("/api/preguntas")
def api_questions():
    ensure_wellbeing_questions()
    questions = list_active_questions()
    return jsonify({"preguntas": [serialize_question(question) for question in questions], "total": len(questions)})


@bp.route("/api/encuesta/<string:folio>")
def api_get_survey(folio: str):
    survey_record = BienestarEncuesta.query.filter_by(hash_id=folio.strip().upper()).first_or_404()
    return jsonify(
        {
            "hash": survey_record.hash_id,
            "estado": survey_record.estado,
            "ultima_pregunta": survey_record.ultima_pregunta,
            "estrato": survey_record.estrato,
            "respuestas": [
                {"id": response.pregunta_id, "dim": response.dimension, "val": response.valor}
                for response in survey_record.respuestas
            ],
            "iibp": round(survey_record.iibp, 2) if survey_record.iibp is not None else None,
            "ivsp": round(survey_record.ivsp, 2) if survey_record.ivsp is not None else None,
        }
    )


@bp.route("/api/encuesta/iniciar", methods=["POST"])
def api_start_survey():
    ensure_wellbeing_questions()
    payload = request.get_json(silent=True) or {}
    estrato = (payload.get("estrato") or DEFAULT_WELLBEING_STRATA[0]).strip().upper()
    if estrato not in DEFAULT_WELLBEING_STRATA:
        estrato = DEFAULT_WELLBEING_STRATA[0]

    survey_record = BienestarEncuesta(
        hash_id=uuid4().hex[:10].upper(),
        estrato=estrato,
        estado="abandonada",
    )
    db.session.add(survey_record)
    db.session.commit()
    log_activity("start_wellbeing_survey", entity_type="bienestar_encuesta", entity_id=survey_record.id, metadata={"estrato": estrato})
    return jsonify({"hash": survey_record.hash_id, "total": len(list_active_questions())})


@bp.route("/api/encuesta/guardar", methods=["POST"])
def api_save_survey():
    payload = request.get_json(silent=True) or {}
    folio = (payload.get("hash") or "").strip().upper()
    if not folio:
        return jsonify({"ok": False, "mensaje": "Falta el folio de la encuesta."}), 400

    survey_record = BienestarEncuesta.query.filter_by(hash_id=folio).first()
    if survey_record is None:
        return jsonify({"ok": False, "mensaje": "Encuesta no encontrada."}), 404

    ok, error = persist_wellbeing_progress(
        survey_record,
        payload.get("respuestas", []),
        requested_state=payload.get("estado"),
        ultima_pregunta=payload.get("ultima_pregunta", 0),
    )
    if not ok:
        return jsonify({"ok": False, "mensaje": error}), 400

    db.session.commit()
    log_activity(
        "save_wellbeing_survey",
        entity_type="bienestar_encuesta",
        entity_id=survey_record.id,
        metadata={"estado": survey_record.estado, "ultima_pregunta": survey_record.ultima_pregunta},
    )
    return jsonify(
        {
            "ok": True,
            "estado": survey_record.estado,
            "iibp": round(survey_record.iibp, 2) if survey_record.iibp is not None else None,
            "ivsp": round(survey_record.ivsp, 2) if survey_record.ivsp is not None else None,
            "redirect_url": url_for("wellbeing.thanks") if survey_record.estado == "completada" else None,
        }
    )
