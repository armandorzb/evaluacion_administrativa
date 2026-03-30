from __future__ import annotations

import csv
import unicodedata
from collections import Counter, defaultdict
from io import StringIO

from municipal_diagnostico.extensions import db
from municipal_diagnostico.models import BienestarEncuesta, BienestarPregunta, BienestarRespuesta
from municipal_diagnostico.timeutils import to_localtime, utcnow
from municipal_diagnostico.wellbeing_seed import DEFAULT_WELLBEING_QUESTIONS, DEFAULT_WELLBEING_STRATA


WELLBEING_STATE_LABELS = {
    "abandonada": "Abandonada",
    "en_progreso": "En progreso",
    "completada": "Completada",
}

WELLBEING_DIMENSION_LABELS = {
    "bienestar psicologico": "Bienestar Psicológico",
    "situacion socioeconomica": "Situación Socioeconómica",
    "salud fisica": "Salud Física",
    "demandas laborales": "Demandas Laborales",
    "recursos organizacionales": "Recursos Organizacionales",
    "apoyo familiar": "Apoyo Familiar",
}


def _canonical_spanish(value: str) -> str:
    cleaned = " ".join((value or "").strip().split()).lower()
    cleaned = cleaned.replace("Â", "").replace("¿", "").replace("?", "")
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", cleaned)
        if not unicodedata.combining(character)
    )


def normalize_wellbeing_dimension(dimension: str) -> str:
    cleaned = " ".join((dimension or "").strip().split())
    if not cleaned:
        return ""
    return WELLBEING_DIMENSION_LABELS.get(_canonical_spanish(cleaned), cleaned)


def normalize_wellbeing_question_text(text: str) -> str:
    cleaned = " ".join((text or "").strip().split())
    if not cleaned:
        return ""

    cleaned = cleaned.lstrip("Â¿").strip()
    cleaned = cleaned.rstrip("?").strip()
    if not cleaned:
        return ""

    return f"¿{cleaned}?"


def ensure_wellbeing_questions() -> None:
    existing_questions = BienestarPregunta.query.order_by(BienestarPregunta.orden.asc()).all()
    if not existing_questions:
        for order, item in enumerate(DEFAULT_WELLBEING_QUESTIONS, start=1):
            db.session.add(
                BienestarPregunta(
                    orden=order,
                    dimension=normalize_wellbeing_dimension(item["dimension"]),
                    texto=normalize_wellbeing_question_text(item["texto"]),
                    opciones=item["opciones"],
                    activa=True,
                )
            )
        db.session.commit()
        return

    dirty = False
    defaults_by_order = {index: item for index, item in enumerate(DEFAULT_WELLBEING_QUESTIONS, start=1)}
    for question in existing_questions:
        normalized_dimension = normalize_wellbeing_dimension(question.dimension)
        if question.dimension != normalized_dimension:
            question.dimension = normalized_dimension
            dirty = True
        normalized_text = normalize_wellbeing_question_text(question.texto)
        if question.texto != normalized_text:
            question.texto = normalized_text
            dirty = True

        default_item = defaults_by_order.get(question.orden)
        if not default_item:
            continue

        default_dimension = normalize_wellbeing_dimension(default_item["dimension"])
        if _canonical_spanish(question.dimension) == _canonical_spanish(default_dimension) and question.dimension != default_dimension:
            question.dimension = default_dimension
            dirty = True

        default_text = normalize_wellbeing_question_text(default_item["texto"])
        if _canonical_spanish(question.texto) == _canonical_spanish(default_text) and question.texto != default_text:
            question.texto = default_text
            dirty = True

        normalized_options = list(default_item["opciones"])
        if len(question.opciones) == len(normalized_options) and all(
            _canonical_spanish(current_option) == _canonical_spanish(expected_option)
            for current_option, expected_option in zip(question.opciones, normalized_options)
        ):
            if question.opciones != normalized_options:
                question.opciones = normalized_options
                dirty = True

    if dirty:
        db.session.commit()


def list_active_questions() -> list[BienestarPregunta]:
    return (
        BienestarPregunta.query.filter_by(activa=True)
        .order_by(BienestarPregunta.orden.asc())
        .all()
    )


def serialize_question(question: BienestarPregunta) -> dict:
    return {
        "id": question.id,
        "orden": question.orden,
        "dim": question.dimension,
        "txt": normalize_wellbeing_question_text(question.texto),
        "opc": [4, 3, 2, 1],
        "t_opc": question.opciones,
    }


def humanize_wellbeing_state(state: str) -> str:
    return WELLBEING_STATE_LABELS.get(state, state.replace("_", " ").capitalize())


def validate_question_payload(form_data) -> tuple[dict | None, str | None]:
    dimension = normalize_wellbeing_dimension(form_data.get("dimension") or "")
    texto = normalize_wellbeing_question_text(form_data.get("texto") or "")
    order = form_data.get("orden", type=int)
    options = [(form_data.get(f"opcion_{index}") or "").strip() for index in range(1, 5)]

    if not dimension:
        return None, "Captura la dimensión."
    if not texto:
        return None, "Captura el texto de la pregunta."
    if order is None or order <= 0:
        return None, "Captura un orden válido."
    if any(not option for option in options):
        return None, "Completa las cuatro opciones de respuesta."

    return {
        "dimension": dimension,
        "texto": texto,
        "orden": order,
        "opciones": options,
    }, None


def question_order_exists(order: int, current_id: int | None = None) -> bool:
    query = BienestarPregunta.query.filter_by(orden=order)
    if current_id is not None:
        query = query.filter(BienestarPregunta.id != current_id)
    return db.session.query(query.exists()).scalar()


def build_wellbeing_dashboard_summary() -> dict:
    surveys = BienestarEncuesta.query.order_by(BienestarEncuesta.created_at.desc()).all()
    completed = [survey for survey in surveys if survey.estado == "completada"]
    abandoned = [survey for survey in surveys if survey.estado == "abandonada"]

    avg_iibp = round(sum(survey.iibp or 0 for survey in completed) / len(completed), 1) if completed else 0.0
    avg_ivsp = round(sum(survey.ivsp or 0 for survey in completed) / len(completed), 1) if completed else 0.0

    strata_counts = {key: 0 for key in DEFAULT_WELLBEING_STRATA}
    dimension_buckets: dict[str, dict[str, float]] = defaultdict(lambda: {"sum": 0.0, "count": 0})

    for survey in completed:
        strata_counts[survey.estrato] = strata_counts.get(survey.estrato, 0) + 1
        for response in survey.respuestas:
            bucket = dimension_buckets[response.dimension]
            bucket["sum"] += response.valor
            bucket["count"] += 1

    dimensions = []
    for dimension, data in sorted(dimension_buckets.items()):
        average = round(data["sum"] / data["count"], 2) if data["count"] else 0.0
        dimensions.append(
            {
                "name": dimension,
                "average": average,
                "percent": round((average / 4) * 100, 1) if average else 0.0,
                "count": int(data["count"]),
            }
        )
    dimensions.sort(key=lambda row: (row["percent"], row["name"]), reverse=True)

    history = []
    for survey in surveys:
        response_map = {response.pregunta_id: response.valor for response in survey.respuestas}
        local_created = to_localtime(survey.created_at)
        history.append(
            {
                "hash": survey.hash_id,
                "fecha": local_created.strftime("%d/%m/%Y %H:%M") if local_created else "-",
                "estrato": survey.estrato,
                "estado": survey.estado,
                "estado_label": humanize_wellbeing_state(survey.estado),
                "ultima_pregunta": survey.ultima_pregunta,
                "iibp": round(survey.iibp, 1) if survey.iibp is not None else None,
                "ivsp": round(survey.ivsp, 1) if survey.ivsp is not None else None,
                "respuestas": response_map,
            }
        )

    completion_rate = round((len(completed) / len(surveys)) * 100, 1) if surveys else 0.0
    return {
        "total": len(surveys),
        "completadas": len(completed),
        "abandonadas": len(abandoned),
        "en_progreso": len([survey for survey in surveys if survey.estado == "en_progreso"]),
        "avg_iibp": avg_iibp,
        "avg_ivsp": avg_ivsp,
        "completion_rate": completion_rate,
        "strata_counts": strata_counts,
        "dimensions": dimensions,
        "history": history,
        "recent_completed": completed[:5],
        "state_counts": Counter(survey.estado for survey in surveys),
    }


def _empty_metric_bucket() -> dict[str, float]:
    return {"sum": 0.0, "count": 0}


def _metric_from_bucket(bucket: dict[str, float]) -> dict[str, float | int | None]:
    count = int(bucket["count"])
    if not count:
        return {"average": None, "percent": None, "count": 0}

    average = round(bucket["sum"] / count, 2)
    return {
        "average": average,
        "percent": round((average / 4) * 100, 1),
        "count": count,
    }


def build_wellbeing_report_payload() -> dict:
    summary = build_wellbeing_dashboard_summary()
    questions = BienestarPregunta.query.order_by(BienestarPregunta.orden.asc()).all()
    surveys = BienestarEncuesta.query.order_by(BienestarEncuesta.created_at.desc()).all()
    completed = [survey for survey in surveys if survey.estado == "completada"]

    dimension_order = list(dict.fromkeys(question.dimension for question in questions))
    strata_order = list(dict.fromkeys([*DEFAULT_WELLBEING_STRATA, *(survey.estrato for survey in completed)]))

    question_buckets = {
        question.id: {
            "overall": _empty_metric_bucket(),
            "by_stratum": {stratum: _empty_metric_bucket() for stratum in strata_order},
        }
        for question in questions
    }
    strata_buckets = {
        stratum: {
            "completed": 0,
            "iibp_sum": 0.0,
            "ivsp_sum": 0.0,
            "dimensions": defaultdict(_empty_metric_bucket),
        }
        for stratum in strata_order
    }

    for survey in completed:
        stratum = survey.estrato
        strata_bucket = strata_buckets.setdefault(
            stratum,
            {
                "completed": 0,
                "iibp_sum": 0.0,
                "ivsp_sum": 0.0,
                "dimensions": defaultdict(_empty_metric_bucket),
            },
        )
        strata_bucket["completed"] += 1
        strata_bucket["iibp_sum"] += survey.iibp or 0.0
        strata_bucket["ivsp_sum"] += survey.ivsp or 0.0

        for response in survey.respuestas:
            question_bucket = question_buckets.get(response.pregunta_id)
            if question_bucket is None:
                continue
            question_bucket["overall"]["sum"] += response.valor
            question_bucket["overall"]["count"] += 1
            stratum_bucket = question_bucket["by_stratum"].setdefault(stratum, _empty_metric_bucket())
            stratum_bucket["sum"] += response.valor
            stratum_bucket["count"] += 1

            dimension_bucket = strata_bucket["dimensions"][response.dimension]
            dimension_bucket["sum"] += response.valor
            dimension_bucket["count"] += 1

    strata_sections = []
    total_completed = len(completed)
    for stratum in strata_order:
        bucket = strata_buckets.get(stratum) or {
            "completed": 0,
            "iibp_sum": 0.0,
            "ivsp_sum": 0.0,
            "dimensions": defaultdict(_empty_metric_bucket),
        }
        dimensions = []
        for dimension in dimension_order:
            metric = _metric_from_bucket(bucket["dimensions"].get(dimension, _empty_metric_bucket()))
            dimensions.append(
                {
                    "name": dimension,
                    "average": metric["average"],
                    "percent": metric["percent"],
                    "count": metric["count"],
                }
            )

        dimensions_with_data = [row for row in dimensions if row["count"]]
        strongest_dimension = max(dimensions_with_data, key=lambda row: row["percent"])["name"] if dimensions_with_data else None
        attention_dimension = min(dimensions_with_data, key=lambda row: row["percent"])["name"] if dimensions_with_data else None
        completed_count = bucket["completed"]
        strata_sections.append(
            {
                "stratum": stratum,
                "completed": completed_count,
                "avg_iibp": round(bucket["iibp_sum"] / completed_count, 1) if completed_count else None,
                "avg_ivsp": round(bucket["ivsp_sum"] / completed_count, 1) if completed_count else None,
                "share_of_completed": round((completed_count / total_completed) * 100, 1) if total_completed else 0.0,
                "dimensions": dimensions,
                "strongest_dimension": strongest_dimension,
                "attention_dimension": attention_dimension,
            }
        )

    question_rows = []
    for question in questions:
        bucket = question_buckets.get(question.id) or {
            "overall": _empty_metric_bucket(),
            "by_stratum": {stratum: _empty_metric_bucket() for stratum in strata_order},
        }
        question_rows.append(
            {
                "id": question.id,
                "orden": question.orden,
                "dimension": question.dimension,
                "texto": normalize_wellbeing_question_text(question.texto),
                "activa": question.activa,
                "state_label": "Activa" if question.activa else "Inactiva",
                "overall": _metric_from_bucket(bucket["overall"]),
                "by_stratum": {
                    stratum: _metric_from_bucket(bucket["by_stratum"].get(stratum, _empty_metric_bucket()))
                    for stratum in strata_order
                },
            }
        )

    question_groups = []
    for dimension in dimension_order:
        dimension_rows = [row for row in question_rows if row["dimension"] == dimension]
        question_groups.append({"dimension": dimension, "rows": dimension_rows})

    dimensions_with_data = [row for row in summary["dimensions"] if row["count"]]
    most_represented_stratum = max(strata_sections, key=lambda row: (row["completed"], row["stratum"])) if strata_sections else None
    executive_notes = []
    if total_completed:
        if most_represented_stratum and most_represented_stratum["completed"]:
            executive_notes.append(
                f"El estrato {most_represented_stratum['stratum']} concentra {most_represented_stratum['completed']} encuestas completadas ({most_represented_stratum['share_of_completed']}% del total)."
            )
        if dimensions_with_data:
            strongest = max(dimensions_with_data, key=lambda row: row["percent"])
            weakest = min(dimensions_with_data, key=lambda row: row["percent"])
            executive_notes.append(
                f"La dimensión mejor posicionada es {strongest['name']} con {strongest['percent']} puntos porcentuales, mientras que {weakest['name']} representa la principal oportunidad de intervención."
            )
        executive_notes.append(
            f"El módulo acumula una tasa de finalización de {summary['completion_rate']}% con {summary['en_progreso']} encuestas aún en progreso."
        )
    else:
        executive_notes.append(
            "Aún no hay encuestas completadas; el reporte presenta la estructura ejecutiva y el anexo técnico listos para consolidar resultados en cuanto se cierre la primera muestra."
        )

    return {
        "summary": summary,
        "questions": questions,
        "question_rows": question_rows,
        "question_groups": question_groups,
        "strata": strata_sections,
        "strata_order": strata_order,
        "dimension_order": dimension_order,
        "executive_notes": executive_notes,
    }


def persist_wellbeing_progress(
    survey: BienestarEncuesta,
    responses_payload: list[dict],
    *,
    requested_state: str | None = None,
    ultima_pregunta: int = 0,
) -> tuple[bool, str | None]:
    active_questions = list_active_questions()
    question_map = {question.id: question for question in active_questions}

    if not question_map:
        return False, "No hay preguntas activas para responder."

    cleaned_payload = []
    seen_question_ids: set[int] = set()
    for entry in responses_payload:
        question_id = int(entry.get("id")) if entry.get("id") is not None else None
        value = int(entry.get("val")) if entry.get("val") is not None else None
        if question_id is None or value is None:
            continue
        if question_id not in question_map:
            return False, "La respuesta incluye una pregunta no válida."
        if question_id in seen_question_ids:
            continue
        if value not in {1, 2, 3, 4}:
            return False, "Las respuestas deben estar en escala de 1 a 4."
        seen_question_ids.add(question_id)
        cleaned_payload.append((question_map[question_id], value))

    requested_state = (requested_state or "").strip().lower()
    if requested_state == "completada" and len(cleaned_payload) != len(question_map):
        return False, "Debes responder todas las preguntas antes de completar la encuesta."

    db.session.query(BienestarRespuesta).filter_by(encuesta_id=survey.id).delete()
    for question, value in cleaned_payload:
        db.session.add(
            BienestarRespuesta(
                encuesta_id=survey.id,
                pregunta_id=question.id,
                dimension=question.dimension,
                valor=value,
            )
        )

    survey.ultima_pregunta = max(0, min(int(ultima_pregunta or 0), len(question_map)))

    if requested_state == "completada":
        iibp = round((sum(value for _question, value in cleaned_payload) / (len(question_map) * 4)) * 100, 2)
        ivsp = round(min(100 - iibp + 5, 100), 2)
        survey.iibp = iibp
        survey.ivsp = ivsp
        survey.estado = "completada"
        survey.completada_at = utcnow()
    else:
        survey.iibp = None
        survey.ivsp = None
        survey.completada_at = None
        survey.estado = "en_progreso" if cleaned_payload else "abandonada"

    return True, None


def build_wellbeing_csv() -> str:
    summary = build_wellbeing_dashboard_summary()
    questions = BienestarPregunta.query.order_by(BienestarPregunta.orden.asc()).all()

    buffer = StringIO()
    writer = csv.writer(buffer)
    header = [
        "hash",
        "fecha",
        "estrato",
        "estado",
        "ultima_pregunta",
        "iibp",
        "ivsp",
    ]
    header.extend([f"pregunta_{question.orden}" for question in questions])
    writer.writerow(header)

    for row in summary["history"]:
        values = [
            row["hash"],
            row["fecha"],
            row["estrato"],
            row["estado_label"],
            row["ultima_pregunta"],
            row["iibp"] if row["iibp"] is not None else "",
            row["ivsp"] if row["ivsp"] is not None else "",
        ]
        for question in questions:
            values.append(row["respuestas"].get(question.id, ""))
        writer.writerow(values)

    return buffer.getvalue()
