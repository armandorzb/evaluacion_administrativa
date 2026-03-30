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
