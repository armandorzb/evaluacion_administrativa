from __future__ import annotations

from collections import Counter

from municipal_diagnostico.extensions import db
from municipal_diagnostico.iso9001_seed_data import ISO9001_VERSION
from municipal_diagnostico.models import (
    Iso9001Apartado,
    Iso9001Clausula,
    Iso9001CuestionarioVersion,
    Iso9001Evaluacion,
    Iso9001Reactivo,
)
from municipal_diagnostico.timeutils import to_localtime, utcnow


ISO9001_OPTION_LABELS = {
    "no": "No",
    "parcial": "Parcial",
    "si": "Sí",
    "na": "N/A",
}

ISO9001_OPTION_POINTS = {
    "no": 0,
    "parcial": 1,
    "si": 2,
    "na": None,
}

ISO9001_EVALUATION_STATES = {
    "borrador": "Borrador",
    "en_captura": "En captura",
    "en_revision": "En revisión",
    "devuelta": "Devuelta",
    "cerrada": "Cerrada",
}

ISO9001_CYCLE_STATES = {
    "borrador": "Borrador",
    "activo": "Activo",
    "cerrado": "Cerrado",
}

ISO9001_FINAL_STATES = {"cerrada"}


def ensure_iso9001_catalog() -> Iso9001CuestionarioVersion:
    version = Iso9001CuestionarioVersion.query.filter_by(slug=ISO9001_VERSION["slug"]).first()
    if version:
        if sync_iso9001_catalog_texts(version):
            db.session.commit()
        return version

    version = Iso9001CuestionarioVersion(
        slug=ISO9001_VERSION["slug"],
        nombre=ISO9001_VERSION["nombre"],
        descripcion=ISO9001_VERSION["descripcion"],
        norma=ISO9001_VERSION["norma"],
        estado="publicado",
        publicado_at=utcnow(),
    )
    db.session.add(version)
    db.session.flush()

    for clause_payload in ISO9001_VERSION["clausulas"]:
        clause = Iso9001Clausula(
            version=version,
            numero=clause_payload["numero"],
            nombre=clause_payload["nombre"],
            orden=clause_payload["orden"],
        )
        db.session.add(clause)
        db.session.flush()

        for section_payload in clause_payload["apartados"]:
            section = Iso9001Apartado(
                clausula=clause,
                codigo=section_payload["codigo"],
                nombre=section_payload["nombre"],
                orden=section_payload["orden"],
            )
            db.session.add(section)
            db.session.flush()

            for reactive_payload in section_payload["reactivos"]:
                db.session.add(
                    Iso9001Reactivo(
                        apartado=section,
                        numero=reactive_payload["numero"],
                        orden=reactive_payload["orden"],
                        texto=reactive_payload["texto"],
                        evidencia_sugerida=reactive_payload["evidencia_sugerida"],
                        criterio_idoneidad=reactive_payload["criterio_idoneidad"],
                    )
                )

    db.session.commit()
    return version


def sync_iso9001_catalog_texts(version: Iso9001CuestionarioVersion) -> bool:
    changed = False

    changed |= _assign_if_changed(version, "nombre", ISO9001_VERSION["nombre"])
    changed |= _assign_if_changed(version, "descripcion", ISO9001_VERSION["descripcion"])
    changed |= _assign_if_changed(version, "norma", ISO9001_VERSION["norma"])

    clauses_by_number = {clause.numero: clause for clause in version.clausulas}
    for clause_payload in ISO9001_VERSION["clausulas"]:
        clause = clauses_by_number.get(clause_payload["numero"])
        if clause is None:
            continue
        changed |= _assign_if_changed(clause, "nombre", clause_payload["nombre"])

        sections_by_code = {section.codigo: section for section in clause.apartados}
        for section_payload in clause_payload["apartados"]:
            section = sections_by_code.get(section_payload["codigo"])
            if section is None:
                continue
            changed |= _assign_if_changed(section, "nombre", section_payload["nombre"])

            reactives_by_number = {reactive.numero: reactive for reactive in section.reactivos}
            for reactive_payload in section_payload["reactivos"]:
                reactive = reactives_by_number.get(reactive_payload["numero"])
                if reactive is None:
                    continue
                changed |= _assign_if_changed(reactive, "texto", reactive_payload["texto"])
                changed |= _assign_if_changed(reactive, "evidencia_sugerida", reactive_payload["evidencia_sugerida"])
                changed |= _assign_if_changed(reactive, "criterio_idoneidad", reactive_payload["criterio_idoneidad"])

    return changed


def _assign_if_changed(model, field: str, value) -> bool:
    if getattr(model, field) == value:
        return False
    setattr(model, field, value)
    return True


def latest_iso9001_version() -> Iso9001CuestionarioVersion:
    return ensure_iso9001_catalog()


def humanize_iso9001_state(state: str) -> str:
    return ISO9001_EVALUATION_STATES.get(state, state.replace("_", " ").capitalize())


def humanize_iso9001_cycle_state(state: str) -> str:
    return ISO9001_CYCLE_STATES.get(state, state.replace("_", " ").capitalize())


def maturity_label(percent: float | None) -> tuple[str, str]:
    if percent is None:
        return "Sin evaluar", "empty"
    if percent == 0:
        return "Nivel 0 - No iniciado", "low"
    if percent <= 20:
        return "Nivel 1 - Inicial", "low"
    if percent <= 40:
        return "Nivel 2 - En desarrollo", "medium"
    if percent <= 60:
        return "Nivel 3 - Definido", "medium"
    if percent <= 80:
        return "Nivel 4 - Gestionado", "high"
    return "Nivel 5 - Optimizado", "optimal"


def score_percent(points: int, applicable: int) -> float | None:
    if applicable <= 0:
        return None
    return round((points / (applicable * 2)) * 100, 2)


def summarize_iso9001_evaluation(evaluation: Iso9001Evaluacion) -> dict:
    version = evaluation.ciclo.version
    response_map = {response.reactivo_id: response for response in evaluation.respuestas}
    clauses = []
    sections = []
    total_questions = 0
    answered_questions = 0
    applicable_questions = 0
    total_points = 0
    evidence_count = 0

    for clause in version.clausulas:
        clause_totals = _empty_totals()
        clause_sections = []
        for section in clause.apartados:
            section_totals = _empty_totals()
            question_rows = []
            for reactive in section.reactivos:
                response = response_map.get(reactive.id)
                evidence_rows = [evidence for evidence in (response.evidencias if response else []) if evidence.activo]
                row = _question_summary(reactive, response, evidence_rows)
                question_rows.append(row)
                _accumulate(section_totals, row)
                _accumulate(clause_totals, row)
                total_questions += 1
                answered_questions += 1 if row["answered"] else 0
                applicable_questions += 1 if row["applicable"] else 0
                total_points += row["points"]
                evidence_count += len(evidence_rows)

            section_percent = score_percent(section_totals["points"], section_totals["applicable"])
            section_label, section_slug = maturity_label(section_percent)
            section_summary = {
                "id": section.id,
                "codigo": section.codigo,
                "nombre": section.nombre,
                "clausula": clause.numero,
                "questions": question_rows,
                "total": section_totals["total"],
                "answered": section_totals["answered"],
                "applicable": section_totals["applicable"],
                "na": section_totals["na"],
                "points": section_totals["points"],
                "completion": _completion(section_totals["answered"], section_totals["total"]),
                "percent": section_percent,
                "maturity_label": section_label,
                "maturity_slug": section_slug,
            }
            sections.append(section_summary)
            clause_sections.append(section_summary)

        clause_percent = score_percent(clause_totals["points"], clause_totals["applicable"])
        clause_label, clause_slug = maturity_label(clause_percent)
        clauses.append(
            {
                "id": clause.id,
                "numero": clause.numero,
                "nombre": clause.nombre,
                "sections": clause_sections,
                "total": clause_totals["total"],
                "answered": clause_totals["answered"],
                "applicable": clause_totals["applicable"],
                "na": clause_totals["na"],
                "points": clause_totals["points"],
                "completion": _completion(clause_totals["answered"], clause_totals["total"]),
                "percent": clause_percent,
                "maturity_label": clause_label,
                "maturity_slug": clause_slug,
            }
        )

    global_percent = score_percent(total_points, applicable_questions)
    global_label, global_slug = maturity_label(global_percent)
    evaluation.progreso = _completion(answered_questions, total_questions)

    return {
        "evaluation": evaluation,
        "state_label": humanize_iso9001_state(evaluation.estado),
        "total_questions": total_questions,
        "answered_questions": answered_questions,
        "applicable_questions": applicable_questions,
        "na_questions": answered_questions - applicable_questions,
        "points": total_points,
        "completion": evaluation.progreso,
        "percent": global_percent,
        "maturity_label": global_label,
        "maturity_slug": global_slug,
        "clauses": clauses,
        "sections": sections,
        "evidence_count": evidence_count,
        "is_final": evaluation.estado in ISO9001_FINAL_STATES,
    }


def summarize_iso9001_cycle(cycle, role: str = "administrador", user=None) -> dict:
    rows = []
    state_counts = Counter(evaluation.estado for evaluation in cycle.evaluaciones)
    for evaluation in cycle.evaluaciones:
        if not _can_include_cycle_evaluation(evaluation, role=role, user=user):
            continue
        summary = summarize_iso9001_evaluation(evaluation)
        rows.append(
            {
                "evaluacion": evaluation,
                "dependencia": evaluation.dependencia.nombre,
                "responsable": evaluation.responsable.nombre if evaluation.responsable else "Sin responsable",
                "revisor": evaluation.revisor.nombre if evaluation.revisor else "Sin revisor",
                "estado": evaluation.estado,
                "estado_label": summary["state_label"],
                "avance": summary["completion"],
                "cumplimiento": summary["percent"],
                "madurez": summary["maturity_label"],
                "maturity_slug": summary["maturity_slug"],
            }
        )
    rows.sort(key=lambda row: (row["avance"], row["cumplimiento"] or -1, row["dependencia"]), reverse=True)
    return {
        "cycle": cycle,
        "rows": rows,
        "visible_total": len(rows),
        "total": len(cycle.evaluaciones),
        "closed_count": state_counts.get("cerrada", 0),
        "review_count": state_counts.get("en_revision", 0),
        "avg_completion": round(sum(row["avance"] for row in rows) / len(rows), 2) if rows else 0,
        "avg_percent": round(sum((row["cumplimiento"] or 0) for row in rows) / len(rows), 2) if rows else None,
        "state_counts": state_counts,
    }


def _can_include_cycle_evaluation(evaluation: Iso9001Evaluacion, role: str, user=None) -> bool:
    if user is None:
        return role != "consulta" or evaluation.estado in ISO9001_FINAL_STATES
    if user.rol == "administrador":
        return True
    if any(assignment.usuario_id == user.id and assignment.tipo == "captura" for assignment in evaluation.asignaciones):
        return True
    if user.rol == "consulta":
        return evaluation.estado in ISO9001_FINAL_STATES
    if user.rol == "revisor":
        return evaluation.revisor_id == user.id or evaluation.estado in ISO9001_FINAL_STATES
    return any(assignment.usuario_id == user.id for assignment in evaluation.asignaciones)


def list_visible_iso9001_evaluations(user) -> list[Iso9001Evaluacion]:
    query = Iso9001Evaluacion.query.order_by(Iso9001Evaluacion.updated_at.desc())
    evaluations = query.all()
    if user.rol == "administrador":
        return evaluations
    if user.rol == "revisor":
        return [
            evaluation
            for evaluation in evaluations
            if evaluation.revisor_id == user.id
            or evaluation.estado in ISO9001_FINAL_STATES
            or any(assignment.usuario_id == user.id and assignment.tipo == "captura" for assignment in evaluation.asignaciones)
        ]
    if user.rol == "consulta":
        return [
            evaluation
            for evaluation in evaluations
            if evaluation.estado in ISO9001_FINAL_STATES
            or any(assignment.usuario_id == user.id and assignment.tipo == "captura" for assignment in evaluation.asignaciones)
        ]
    return [
        evaluation
        for evaluation in evaluations
        if any(assignment.usuario_id == user.id for assignment in evaluation.asignaciones)
    ]


def _empty_totals() -> dict:
    return {"total": 0, "answered": 0, "applicable": 0, "na": 0, "points": 0}


def _accumulate(totals: dict, row: dict) -> None:
    totals["total"] += 1
    totals["answered"] += 1 if row["answered"] else 0
    totals["applicable"] += 1 if row["applicable"] else 0
    totals["na"] += 1 if row["is_na"] else 0
    totals["points"] += row["points"]


def _question_summary(reactive: Iso9001Reactivo, response, evidence_rows: list) -> dict:
    answered = response is not None
    selected = response.calificacion if response else None
    is_na = selected == "na"
    points = response.valor if response and response.valor is not None else 0
    return {
        "reactivo": reactive,
        "response": response,
        "answered": answered,
        "selected": selected,
        "selected_label": ISO9001_OPTION_LABELS.get(selected, "Sin respuesta"),
        "is_na": is_na,
        "applicable": answered and not is_na,
        "points": points,
        "observacion": response.observacion if response else "",
        "evidence": evidence_rows,
    }


def _completion(answered: int, total: int) -> float:
    return round((answered / total) * 100, 2) if total else 0.0


def format_iso_datetime(value) -> str:
    local_value = to_localtime(value)
    if local_value is None:
        return "Sin registro"
    return local_value.strftime("%d/%m/%Y %H:%M")
