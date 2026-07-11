from __future__ import annotations

from collections import Counter

from municipal_diagnostico.extensions import db
from municipal_diagnostico.iso45001_seed_data import (
    ISO45001_V2_CATALOG_SLUG,
    ISO45001_V2_VERSION,
    ISO45001_VERSION,
)
from municipal_diagnostico.models import (
    Iso45001Apartado,
    Iso45001Clausula,
    Iso45001ControlEvidencia,
    Iso45001ControlEvidenciaPunto,
    Iso45001ControlEvidenciaReactivo,
    Iso45001CuestionarioVersion,
    Iso45001DocumentoRequerido,
    Iso45001EvidenciaDocumental,
    Iso45001EvaluacionControlEvidencia,
    Iso45001EvaluacionControlEvidenciaPunto,
    Iso45001Evaluacion,
    Iso45001Reactivo,
)
from municipal_diagnostico.timeutils import to_localtime, utcnow
from municipal_diagnostico.utils import allowed_file, store_upload


ISO45001_OPTION_LABELS = {
    "no": "No",
    "parcial": "Parcial",
    "si": "Sí",
}

ISO45001_OPTION_POINTS = {
    "no": 0,
    "parcial": 1,
    "si": 2,
}

ISO45001_EVALUATION_STATES = {
    "borrador": "Borrador",
    "en_captura": "En captura",
    "en_revision": "En revisión",
    "devuelta": "Devuelta",
    "cerrada": "Cerrada",
}

ISO45001_CYCLE_STATES = {
    "borrador": "Borrador",
    "activo": "Activo",
    "cerrado": "Cerrado",
}

ISO45001_FINAL_STATES = {"cerrada"}


def ensure_iso45001_catalog() -> Iso45001CuestionarioVersion:
    """Seed immutable ISO 45001 v1 and v2 catalogs and return the current v2.

    The old catalog remains queryable so its cycles and reports keep their
    original evidence semantics.  New cycles use v2, where documents are
    controlled once and may cover several reactives.
    """

    _ensure_iso45001_catalog_version(ISO45001_VERSION)
    return _ensure_iso45001_catalog_version(ISO45001_V2_VERSION)


def _ensure_iso45001_catalog_version(payload: dict) -> Iso45001CuestionarioVersion:
    version = Iso45001CuestionarioVersion.query.filter_by(slug=payload["slug"]).first()
    if version is not None:
        return version

    version = Iso45001CuestionarioVersion(
        slug=payload["slug"],
        nombre=payload["nombre"],
        descripcion=payload["descripcion"],
        norma=payload["norma"],
        estado="publicado",
        publicado_at=utcnow(),
    )
    db.session.add(version)
    db.session.flush()

    documents_by_code: dict[str, Iso45001DocumentoRequerido] = {}
    for document_payload in payload.get("documentos_obligatorios", []):
        document = Iso45001DocumentoRequerido(
            version=version,
            codigo=document_payload["codigo"],
            apartado=document_payload["apartado"],
            clasificacion=document_payload["clasificacion"],
            nombre=document_payload["nombre"],
            contenido_minimo=document_payload["contenido_minimo"],
            criticidad=str(document_payload["criticidad"]),
            orden=document_payload["orden"],
        )
        db.session.add(document)
        documents_by_code[document.codigo] = document

    reactives_by_code: dict[str, Iso45001Reactivo] = {}
    for clause_payload in payload["clausulas"]:
        clause = Iso45001Clausula(
            version=version,
            numero=clause_payload["numero"],
            nombre=clause_payload["nombre"],
            orden=clause_payload["orden"],
        )
        db.session.add(clause)
        db.session.flush()

        for section_payload in clause_payload["apartados"]:
            section = Iso45001Apartado(
                clausula=clause,
                codigo=section_payload["codigo"],
                nombre=section_payload["nombre"],
                orden=section_payload["orden"],
            )
            db.session.add(section)
            db.session.flush()

            for reactive_payload in section_payload["reactivos"]:
                reactive = Iso45001Reactivo(
                    apartado=section,
                    codigo=reactive_payload["codigo"],
                    numero=reactive_payload["numero"],
                    orden=reactive_payload["orden"],
                    tema=reactive_payload["tema"],
                    texto=reactive_payload["texto"],
                    evidencia_sugerida=reactive_payload["evidencia_sugerida"],
                    criterio_idoneidad=reactive_payload["criterio_idoneidad"],
                    criticidad=str(reactive_payload["criticidad"]),
                    es_enmienda_2024=reactive_payload["es_enmienda_2024"],
                    requiere_documento=reactive_payload["requiere_documento"],
                )
                db.session.add(reactive)
                reactives_by_code[reactive.codigo] = reactive

                for document_code in _document_codes(reactive_payload):
                    document = documents_by_code.get(document_code)
                    if document is None:
                        raise ValueError(
                            f"El reactivo ISO 45001 {reactive_payload['codigo']} referencia el documento "
                            f"obligatorio inexistente {document_code}."
                        )
                    reactive.documentos_requeridos.append(document)

    db.session.flush()
    for control_payload in payload.get("controles_evidencia", []):
        control = Iso45001ControlEvidencia(
            version=version,
            codigo=control_payload["codigo"],
            tipo=control_payload["tipo"],
            clausula=control_payload["clausula"],
            apartado=control_payload["apartado"],
            clasificacion=control_payload["clasificacion"],
            nombre=control_payload["nombre"],
            descripcion=control_payload.get("descripcion"),
            contenido_minimo=control_payload.get("contenido_minimo"),
            evidencia_sugerida=control_payload.get("evidencia_sugerida"),
            criticidad=str(control_payload["criticidad"]),
            orden=control_payload["orden"],
        )
        db.session.add(control)
        db.session.flush()
        for point_payload in control_payload.get("puntos", []):
            db.session.add(
                Iso45001ControlEvidenciaPunto(
                    control=control,
                    orden=point_payload["orden"],
                    texto=point_payload["texto"],
                )
            )
        for reactive_code in control_payload.get("reactivos", []):
            reactive = reactives_by_code.get(reactive_code)
            if reactive is None:
                raise ValueError(
                    f"El control ISO 45001 {control.codigo} referencia el reactivo inexistente {reactive_code}."
                )
            db.session.add(Iso45001ControlEvidenciaReactivo(control=control, reactivo=reactive))

    db.session.commit()
    return version


def _document_codes(reactive_payload: dict) -> list[str]:
    raw_codes = reactive_payload.get("documentos_requeridos") or []
    if isinstance(raw_codes, str):
        raw_codes = [raw_codes]
    codes: list[str] = []
    for code in raw_codes:
        normalized = str(code).strip()
        if normalized and normalized not in codes:
            codes.append(normalized)
    return codes


def latest_iso45001_version() -> Iso45001CuestionarioVersion:
    return ensure_iso45001_catalog()


def humanize_iso45001_state(state: str) -> str:
    return ISO45001_EVALUATION_STATES.get(state, state.replace("_", " ").capitalize())


def humanize_iso45001_cycle_state(state: str) -> str:
    return ISO45001_CYCLE_STATES.get(state, state.replace("_", " ").capitalize())


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


def score_percent(points: int, total_questions: int) -> float | None:
    """Return points / all possible points, including unanswered reactives."""

    if total_questions <= 0:
        return None
    return round((points / (total_questions * 2)) * 100, 2)


def uses_document_control_coverage(version: Iso45001CuestionarioVersion) -> bool:
    """Return whether a version evaluates reusable evidence by control."""

    return version.slug == ISO45001_V2_CATALOG_SLUG


def ensure_document_controls_for_evaluation(evaluation: Iso45001Evaluacion, user=None) -> list:
    """Materialize the immutable v2 control checklist for one evaluation.

    The rows are intentionally created per evaluation rather than inferred from
    response files.  This lets a single library file support several controls
    while preserving the coverage declaration and reviewer trail of each one.
    """

    version = evaluation.ciclo.version
    if not uses_document_control_coverage(version) or evaluation.id is None:
        return []

    controls = list(version.controles_evidencia)
    existing = {
        item.control_evidencia_id: item
        for item in evaluation.controles_evidencia
    }
    created = []
    for control in controls:
        assessment = existing.get(control.id)
        if assessment is None:
            assessment = Iso45001EvaluacionControlEvidencia(
                evaluacion=evaluation,
                control=control,
                usuario=user,
                estado="no",
            )
            db.session.add(assessment)
            db.session.flush()
            existing[control.id] = assessment
            created.append(assessment)

        response_point_ids = {
            item.control_evidencia_punto_id
            for item in assessment.puntos
        }
        for point in control.puntos:
            if point.id not in response_point_ids:
                db.session.add(
                    Iso45001EvaluacionControlEvidenciaPunto(
                        evaluacion_control=assessment,
                        punto=point,
                        cubierto=False,
                    )
                )

    if created:
        db.session.flush()
    return [existing[control.id] for control in controls]


def summarize_iso45001_evaluation(evaluation: Iso45001Evaluacion) -> dict:
    """Build the canonical reporting view of an ISO 45001 evaluation.

    Every catalog reactive is applicable.  Therefore capture completion and
    compliance are intentionally independent: compliance always uses the full
    possible score, while completion reflects how much has been answered.
    """

    version = evaluation.ciclo.version
    has_document_controls = uses_document_control_coverage(version)
    if has_document_controls:
        ensure_document_controls_for_evaluation(evaluation)
    response_map = {response.reactivo_id: response for response in evaluation.respuestas}
    document_rows = {
        document.id: _document_summary(document)
        for document in getattr(version, "documentos_obligatorios", ())
    }
    clauses = []
    sections = []
    findings = []
    response_counts: Counter[str] = Counter()
    total_questions = 0
    answered_questions = 0
    total_points = 0
    evidence_count = 0
    evidence_required = 0
    evidence_satisfied = 0

    for clause in version.clausulas:
        clause_totals = _empty_totals()
        clause_sections = []
        for section in clause.apartados:
            section_totals = _empty_totals()
            question_rows = []
            for reactive in section.reactivos:
                response = response_map.get(reactive.id)
                evidence_rows = [evidence for evidence in (response.evidencias if response else []) if evidence.activo]
                row = _question_summary(
                    reactive,
                    response,
                    evidence_rows,
                    require_reactive_evidence=not has_document_controls,
                )
                row["clausula"] = clause.numero
                row["apartado"] = section.codigo
                row["apartado_nombre"] = section.nombre
                question_rows.append(row)
                _accumulate(section_totals, row)
                _accumulate(clause_totals, row)

                total_questions += 1
                answered_questions += int(row["answered"])
                total_points += row["points"]
                evidence_count += len(evidence_rows)
                response_counts[row["selected"] or "sin_respuesta"] += 1
                if row["requires_evidence"]:
                    evidence_required += 1
                    evidence_satisfied += int(row["evidence_satisfied"])

                for document in row["documents"]:
                    document_row = document_rows.setdefault(document.id, _document_summary(document))
                    document_row["questions"].append(row)
                    document_row["mapped_reactives"] += 1
                    document_row["evidence_count"] += len(evidence_rows)
                    document_row["reactives_with_evidence"] += int(bool(evidence_rows))
                    if row["requires_evidence"]:
                        document_row["evidence_required"] += 1
                        document_row["evidence_satisfied"] += int(row["evidence_satisfied"])

                finding = row["finding"]
                if finding is not None:
                    findings.append(finding)

            section_percent = score_percent(section_totals["points"], section_totals["total"])
            section_label, section_slug = maturity_label(section_percent)
            section_summary = {
                "id": section.id,
                "codigo": section.codigo,
                "nombre": section.nombre,
                "clausula": clause.numero,
                "questions": question_rows,
                "total": section_totals["total"],
                "answered": section_totals["answered"],
                "applicable": section_totals["total"],
                "na": 0,
                "points": section_totals["points"],
                "completion": _completion(section_totals["answered"], section_totals["total"]),
                "percent": section_percent,
                "maturity_label": section_label,
                "maturity_slug": section_slug,
                "evidence_count": section_totals["evidence_count"],
                "evidence_coverage": _evidence_coverage(section_totals),
                "finding_count": section_totals["finding_count"],
            }
            sections.append(section_summary)
            clause_sections.append(section_summary)

        clause_percent = score_percent(clause_totals["points"], clause_totals["total"])
        clause_label, clause_slug = maturity_label(clause_percent)
        clauses.append(
            {
                "id": clause.id,
                "numero": clause.numero,
                "nombre": clause.nombre,
                "sections": clause_sections,
                "total": clause_totals["total"],
                "answered": clause_totals["answered"],
                "applicable": clause_totals["total"],
                "na": 0,
                "points": clause_totals["points"],
                "completion": _completion(clause_totals["answered"], clause_totals["total"]),
                "percent": clause_percent,
                "maturity_label": clause_label,
                "maturity_slug": clause_slug,
                "evidence_count": clause_totals["evidence_count"],
                "evidence_coverage": _evidence_coverage(clause_totals),
                "finding_count": clause_totals["finding_count"],
            }
        )

    global_percent = score_percent(total_points, total_questions)
    global_label, global_slug = maturity_label(global_percent)
    evaluation.progreso = _completion(answered_questions, total_questions)
    document_requirements = sorted(document_rows.values(), key=lambda item: (item["orden"], item["codigo"]))
    legacy_evidence_coverage = _evidence_coverage(
        {"evidence_required": evidence_required, "evidence_satisfied": evidence_satisfied}
    )
    # Clause and section identifiers are strings (for example ``10.2``).  Sort
    # their numeric components so the executive report and exported appendices
    # retain the ISO sequence instead of placing clause 10 ahead of clause 4.
    findings.sort(
        key=lambda item: (
            item["priority_order"],
            _iso45001_numeric_key(item["clausula"]),
            _iso45001_numeric_key(item["apartado"]),
            item["reactivo"].orden,
        )
    )

    document_controls = _summarize_document_controls(evaluation) if has_document_controls else []
    document_evidence_stats = _document_evidence_stats(evaluation, document_controls)
    document_validation = _document_control_validation(document_controls)
    if has_document_controls:
        _attach_document_control_coverage(clauses, sections, document_controls)
    evidence_coverage = (
        {
            "required": document_evidence_stats["total_controls"],
            "satisfied": document_evidence_stats["sustained_controls"],
            "missing": len(document_validation["missing_files"]),
            "percent": document_evidence_stats["percent"],
            "mode": "por_control",
        }
        if has_document_controls
        else legacy_evidence_coverage
    )

    return {
        "evaluation": evaluation,
        "state_label": humanize_iso45001_state(evaluation.estado),
        "total_questions": total_questions,
        "answered_questions": answered_questions,
        "applicable_questions": total_questions,
        "na_questions": 0,
        "points": total_points,
        "maximum_points": total_questions * 2,
        "completion": evaluation.progreso,
        "percent": global_percent,
        "maturity_label": global_label,
        "maturity_slug": global_slug,
        "clauses": clauses,
        "sections": sections,
        "evidence_count": document_evidence_stats["file_count"] if has_document_controls else evidence_count,
        "reactive_evidence_count": evidence_count,
        "evidence_coverage": evidence_coverage,
        "document_requirements": document_requirements,
        "documents": document_requirements,
        "document_controls": document_controls,
        "document_evidence_stats": document_evidence_stats,
        "document_validation": document_validation,
        "uses_document_control_coverage": has_document_controls,
        "findings": findings,
        "response_counts": {
            "no": response_counts["no"],
            "parcial": response_counts["parcial"],
            "si": response_counts["si"],
            "sin_respuesta": response_counts["sin_respuesta"],
        },
        "is_final": evaluation.estado in ISO45001_FINAL_STATES,
    }


def validate_iso45001_submission(evaluation: Iso45001Evaluacion) -> dict:
    """Return all blockers for sending or closing an evaluation.

    A draft may be incomplete; this validation is intentionally applied only at
    the workflow gates.  It also treats any legacy/invalid option (including
    ``na``) as an unanswered reactive.
    """

    summary = summarize_iso45001_evaluation(evaluation)
    missing_responses = []
    missing_evidence = []
    for section in summary["sections"]:
        for row in section["questions"]:
            if not row["answered"]:
                missing_responses.append(row)
            elif row["requires_evidence"] and not row["evidence_satisfied"]:
                missing_evidence.append(row)
    document_validation = summary["document_validation"]
    missing_document_controls = document_validation["missing_controls"]
    missing_control_observations = document_validation["missing_observations"]
    missing_control_evidence = document_validation["missing_files"]
    return {
        "ok": not (
            missing_responses
            or missing_evidence
            or missing_document_controls
            or missing_control_observations
            or missing_control_evidence
        ),
        "summary": summary,
        "missing_responses": missing_responses,
        "missing_evidence": missing_evidence,
        "missing_document_controls": missing_document_controls,
        "missing_control_observations": missing_control_observations,
        "missing_control_evidence": missing_control_evidence,
        "document_validation": document_validation,
    }


def summarize_iso45001_cycle(cycle, role: str = "administrador", user=None) -> dict:
    rows = []
    state_counts = Counter(evaluation.estado for evaluation in cycle.evaluaciones)
    for evaluation in cycle.evaluaciones:
        if not _can_include_cycle_evaluation(evaluation, role=role, user=user):
            continue
        summary = summarize_iso45001_evaluation(evaluation)
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
                "evidence_coverage": summary["evidence_coverage"],
                "document_evidence_stats": summary["document_evidence_stats"],
                "document_validation": summary["document_validation"],
                "priority_findings": sum(1 for finding in summary["findings"] if finding["type"] == "brecha_prioritaria"),
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


def list_visible_iso45001_evaluations(user) -> list[Iso45001Evaluacion]:
    evaluations = Iso45001Evaluacion.query.order_by(Iso45001Evaluacion.updated_at.desc()).all()
    if user.rol == "administrador":
        return evaluations
    if user.rol == "revisor":
        return [
            evaluation
            for evaluation in evaluations
            if evaluation.revisor_id == user.id
            or evaluation.estado in ISO45001_FINAL_STATES
            or any(assignment.usuario_id == user.id and assignment.tipo == "captura" for assignment in evaluation.asignaciones)
        ]
    if user.rol == "consulta":
        return [
            evaluation
            for evaluation in evaluations
            if evaluation.estado in ISO45001_FINAL_STATES
            or any(assignment.usuario_id == user.id and assignment.tipo == "captura" for assignment in evaluation.asignaciones)
        ]
    return [
        evaluation
        for evaluation in evaluations
        if any(assignment.usuario_id == user.id for assignment in evaluation.asignaciones)
    ]


def _can_include_cycle_evaluation(evaluation: Iso45001Evaluacion, role: str, user=None) -> bool:
    if user is None:
        return role != "consulta" or evaluation.estado in ISO45001_FINAL_STATES
    if user.rol == "administrador":
        return True
    if any(assignment.usuario_id == user.id and assignment.tipo == "captura" for assignment in evaluation.asignaciones):
        return True
    if user.rol == "consulta":
        return evaluation.estado in ISO45001_FINAL_STATES
    if user.rol == "revisor":
        return evaluation.revisor_id == user.id or evaluation.estado in ISO45001_FINAL_STATES
    return any(assignment.usuario_id == user.id for assignment in evaluation.asignaciones)


def _empty_totals() -> dict:
    return {
        "total": 0,
        "answered": 0,
        "points": 0,
        "evidence_count": 0,
        "evidence_required": 0,
        "evidence_satisfied": 0,
        "finding_count": 0,
    }


def _accumulate(totals: dict, row: dict) -> None:
    totals["total"] += 1
    totals["answered"] += int(row["answered"])
    totals["points"] += row["points"]
    totals["evidence_count"] += len(row["evidence"])
    totals["evidence_required"] += int(row["requires_evidence"])
    totals["evidence_satisfied"] += int(row["requires_evidence"] and row["evidence_satisfied"])
    totals["finding_count"] += int(row["finding"] is not None)


def _evidence_coverage(totals: dict) -> dict:
    required = totals["evidence_required"]
    satisfied = totals["evidence_satisfied"]
    return {
        "required": required,
        "satisfied": satisfied,
        "missing": required - satisfied,
        "percent": _completion(satisfied, required) if required else 100.0,
    }


def _question_summary(
    reactive: Iso45001Reactivo,
    response,
    evidence_rows: list,
    *,
    require_reactive_evidence: bool = True,
) -> dict:
    selected = response.calificacion if response and response.calificacion in ISO45001_OPTION_POINTS else None
    answered = selected is not None
    documents = list(getattr(reactive, "documentos_requeridos", ()) or ())
    # ``requiere_documento`` is the authoritative control flag.  A few source
    # rows deliberately have no one-to-one catalog document mapping, but they
    # still require the evaluator to attach documentary evidence when marked
    # Parcial or Sí.
    has_document_requirement = bool(getattr(reactive, "requiere_documento", False))
    requires_evidence = (
        require_reactive_evidence
        and selected in {"parcial", "si"}
        and has_document_requirement
    )
    evidence_satisfied = bool(evidence_rows) if requires_evidence else True
    points = ISO45001_OPTION_POINTS[selected] if selected is not None else 0
    finding = _finding_for_question(reactive, selected, response, documents)
    return {
        "reactivo": reactive,
        "response": response,
        "answered": answered,
        "selected": selected,
        "selected_label": ISO45001_OPTION_LABELS.get(selected, "Sin respuesta"),
        "is_na": False,
        "applicable": True,
        "points": points,
        "observacion": response.observacion if response else "",
        "evidence": evidence_rows,
        "documents": documents,
        "documentos_requeridos": documents,
        "has_document_requirement": has_document_requirement,
        "requires_evidence": requires_evidence,
        "evidence_satisfied": evidence_satisfied,
        "finding": finding,
    }


def _finding_for_question(reactive, selected: str | None, response, documents: list) -> dict | None:
    if selected == "no":
        finding_type = "brecha_prioritaria"
        finding_label = "Brecha prioritaria"
        priority_order = 0
    elif selected == "parcial":
        finding_type = "brecha_mejora"
        finding_label = "Brecha de mejora"
        priority_order = 1
    else:
        return None
    return {
        "type": finding_type,
        "label": finding_label,
        "priority_order": priority_order,
        "reactivo": reactive,
        "clausula": reactive.apartado.clausula.numero,
        "apartado": reactive.apartado.codigo,
        "apartado_nombre": reactive.apartado.nombre,
        "selected": selected,
        "selected_label": ISO45001_OPTION_LABELS[selected],
        "observacion": response.observacion if response else "",
        "evidencia_sugerida": reactive.evidencia_sugerida,
        "criterio_idoneidad": reactive.criterio_idoneidad,
        "documents": documents,
        "documentos_requeridos": documents,
    }


def _document_summary(document: Iso45001DocumentoRequerido) -> dict:
    return {
        "document": document,
        "codigo": document.codigo,
        "apartado": document.apartado,
        "clasificacion": document.clasificacion,
        "nombre": document.nombre,
        "contenido_minimo": document.contenido_minimo,
        "criticidad": document.criticidad,
        "orden": document.orden,
        "questions": [],
        "mapped_reactives": 0,
        "reactives_with_evidence": 0,
        "evidence_count": 0,
        "evidence_required": 0,
        "evidence_satisfied": 0,
    }


def _summarize_document_controls(evaluation: Iso45001Evaluacion) -> list[dict]:
    """Return the v2 documentary control view used by capture and exports."""

    if not uses_document_control_coverage(evaluation.ciclo.version):
        return []

    assessments = ensure_document_controls_for_evaluation(evaluation)
    rows: list[dict] = []
    for assessment in assessments:
        control = assessment.control
        point_rows = {
            item.control_evidencia_punto_id: item
            for item in assessment.puntos
        }
        points = []
        for point in control.puntos:
            point_response = point_rows.get(point.id)
            points.append(
                {
                    "id": point.id,
                    "response_id": point_response.id if point_response else None,
                    "orden": point.orden,
                    "texto": point.texto,
                    "cubierto": bool(point_response and point_response.cubierto),
                    "observacion": point_response.observacion if point_response else "",
                }
            )
        covered_points = sum(1 for point in points if point["cubierto"])
        total_points = len(points)
        state = _document_control_state(covered_points, total_points)
        evidences = [evidence for evidence in assessment.archivos if evidence.activo]
        observation = _normalise_optional_text(assessment.observacion)
        evaluated = bool(covered_points or evidences or observation)
        rows.append(
            {
                "id": assessment.id,
                "assessment": assessment,
                "catalog_control_id": control.id,
                "codigo": control.codigo,
                "categoria": "normativo" if control.es_normativo else "complementario",
                "tipo": control.tipo,
                "clausula": control.clausula,
                "apartado": control.apartado,
                "clasificacion": control.clasificacion,
                "nombre": control.nombre,
                "descripcion": control.descripcion,
                "contenido_minimo": control.contenido_minimo,
                "evidencia_sugerida": control.evidencia_sugerida,
                "criticidad": control.criticidad,
                "orden": control.orden,
                "estado": state,
                "estado_label": ISO45001_OPTION_LABELS.get(state, "Sin evaluar"),
                "observacion": observation or "",
                "evaluated": evaluated,
                "puntos": points,
                "puntos_cubiertos": covered_points,
                "total_puntos": total_points,
                "coverage_percent": _completion(covered_points, total_points),
                "reactivos": [
                    {
                        "id": reactive.id,
                        "codigo": reactive.codigo,
                        "apartado": reactive.apartado.codigo,
                        "texto": reactive.texto,
                    }
                    for reactive in control.reactivos
                ],
                "evidencias": [_document_evidence_view(evidence) for evidence in evidences],
                "evidence_ids": [evidence.id for evidence in evidences],
                "files_count": len(evidences),
                "requires_file": state in {"parcial", "si"},
            }
        )
    return rows


def _document_evidence_view(evidence: Iso45001EvidenciaDocumental) -> dict:
    return {
        "id": evidence.id,
        "archivo_nombre_original": evidence.archivo_nombre_original,
        "archivo_guardado": evidence.archivo_guardado,
        "mime_type": evidence.mime_type,
        "tamano_bytes": evidence.tamano_bytes,
        "activo": evidence.activo,
        "created_at": evidence.created_at,
    }


def _document_control_state(covered_points: int, total_points: int) -> str:
    if covered_points <= 0:
        return "no"
    if total_points and covered_points >= total_points:
        return "si"
    return "parcial"


def _document_evidence_stats(evaluation: Iso45001Evaluacion, controls: list[dict]) -> dict:
    total_points = sum(control["total_puntos"] for control in controls)
    covered_points = sum(control["puntos_cubiertos"] for control in controls)
    active_evidences = [evidence for evidence in evaluation.evidencias_documentales if evidence.activo]
    sustained = sum(
        1
        for control in controls
        if control["estado"] in {"parcial", "si"} and control["files_count"]
    )
    return {
        "total_controls": len(controls),
        "normative_controls": sum(control["categoria"] == "normativo" for control in controls),
        "complementary_controls": sum(control["categoria"] == "complementario" for control in controls),
        "evaluated_controls": sum(control["evaluated"] for control in controls),
        "covered_points": covered_points,
        "total_points": total_points,
        "percent": _completion(covered_points, total_points),
        "sustained_controls": sustained,
        "covered_controls": sum(control["estado"] == "si" for control in controls),
        "partial_controls": sum(control["estado"] == "parcial" for control in controls),
        "gap_controls": sum(control["estado"] == "no" for control in controls),
        "file_count": len(active_evidences),
        "unlinked_file_count": sum(not evidence.controles_evidencia for evidence in active_evidences),
    }


def _attach_document_control_coverage(
    clauses: list[dict],
    sections: list[dict],
    controls: list[dict],
) -> None:
    """Attach non-scoring documentary coverage to the report's ISO scopes."""

    for clause in clauses:
        clause_controls = [
            control
            for control in controls
            if str(control["clausula"]) == str(clause["numero"])
        ]
        clause["document_control_coverage"] = _document_control_scope_stats(clause_controls)
    for section in sections:
        section_controls = [
            control
            for control in controls
            if str(control["apartado"]) == str(section["codigo"])
        ]
        section["document_control_coverage"] = _document_control_scope_stats(section_controls)


def _document_control_scope_stats(controls: list[dict]) -> dict:
    total_points = sum(int(control["total_puntos"]) for control in controls)
    covered_points = sum(int(control["puntos_cubiertos"]) for control in controls)
    evidence_ids = {
        evidence["id"]
        for control in controls
        for evidence in control["evidencias"]
    }
    sustained_controls = sum(
        control["estado"] in {"parcial", "si"} and bool(control["evidence_ids"])
        for control in controls
    )
    return {
        "total_controls": len(controls),
        "evaluated_controls": sum(bool(control["evaluated"]) for control in controls),
        "covered_points": covered_points,
        "total_points": total_points,
        "percent": _completion(covered_points, total_points),
        "file_count": len(evidence_ids),
        "sustained_controls": sustained_controls,
        "gap_controls": sum(control["evaluated"] and control["estado"] == "no" for control in controls),
        "partial_controls": sum(control["estado"] == "parcial" for control in controls),
        "pending_controls": sum(not control["evaluated"] for control in controls),
    }


def _document_control_validation(controls: list[dict]) -> dict:
    missing_controls = [control for control in controls if not control["evaluated"]]
    missing_observations = [
        control
        for control in controls
        if control["evaluated"] and control["estado"] == "no" and not control["observacion"]
    ]
    missing_files = [
        control
        for control in controls
        if control["evaluated"]
        and control["estado"] in {"parcial", "si"}
        and not control["evidence_ids"]
    ]
    return {
        "missing_controls": missing_controls,
        "missing_observations": missing_observations,
        "missing_files": missing_files,
        "ok": not (missing_controls or missing_observations or missing_files),
    }


def save_document_control_payload(
    evaluation: Iso45001Evaluacion,
    control_id: int,
    payload: dict,
    *,
    user=None,
) -> dict:
    """Persist checklist coverage and reusable-file links for one v2 control."""

    if not uses_document_control_coverage(evaluation.ciclo.version):
        return {"ok": False, "error": "Esta evaluación usa el esquema documental histórico."}
    ensure_document_controls_for_evaluation(evaluation, user=user)
    assessment = next(
        (item for item in evaluation.controles_evidencia if item.id == control_id),
        None,
    )
    if assessment is None:
        return {"ok": False, "error": "El control documental no pertenece a esta evaluación."}

    try:
        selected_point_ids = {int(value) for value in payload.get("punto_ids", [])}
        selected_evidence_ids = {int(value) for value in payload.get("evidencia_ids", [])}
    except (TypeError, ValueError):
        return {"ok": False, "error": "Los identificadores de puntos o archivos no son válidos."}

    allowed_point_ids = {point.id for point in assessment.control.puntos}
    if not selected_point_ids.issubset(allowed_point_ids):
        return {"ok": False, "error": "Se recibieron puntos que no corresponden al control documental."}

    evidence_by_id = {
        evidence.id: evidence
        for evidence in evaluation.evidencias_documentales
        if evidence.activo
    }
    if not selected_evidence_ids.issubset(evidence_by_id):
        return {"ok": False, "error": "Sólo puedes vincular archivos activos de esta evaluación."}

    responses_by_point = {
        response.control_evidencia_punto_id: response
        for response in assessment.puntos
    }
    for point in assessment.control.puntos:
        response = responses_by_point.get(point.id)
        if response is None:
            response = Iso45001EvaluacionControlEvidenciaPunto(
                evaluacion_control=assessment,
                punto=point,
            )
            db.session.add(response)
        response.cubierto = point.id in selected_point_ids

    assessment.archivos = [evidence_by_id[evidence_id] for evidence_id in selected_evidence_ids]
    assessment.observacion = _normalise_optional_text(payload.get("observacion"))
    assessment.estado = _document_control_state(
        len(selected_point_ids),
        len(assessment.control.puntos),
    )
    assessment.usuario = user
    db.session.flush()
    return {"ok": True, "control": assessment}


def upload_document_evidence(
    evaluation: Iso45001Evaluacion,
    uploads: list,
    control_ids: list[int] | None = None,
    *,
    user=None,
) -> dict:
    """Store each upload once and optionally link it to several controls."""

    if not uses_document_control_coverage(evaluation.ciclo.version):
        return {"ok": False, "error": "Esta evaluación usa el esquema documental histórico."}
    ensure_document_controls_for_evaluation(evaluation, user=user)
    files = [upload for upload in uploads if upload and getattr(upload, "filename", "")]
    if not files:
        return {"ok": False, "error": "Selecciona al menos un archivo válido."}
    invalid = [upload.filename for upload in files if not allowed_file(upload.filename)]
    if invalid:
        return {"ok": False, "error": "Formato no permitido: " + ", ".join(invalid)}

    requested_control_ids = {int(value) for value in (control_ids or [])}
    assessments_by_id = {item.id: item for item in evaluation.controles_evidencia}
    if not requested_control_ids.issubset(assessments_by_id):
        return {"ok": False, "error": "Se seleccionó un control que no pertenece a esta evaluación."}

    created = []
    targets = [assessments_by_id[item_id] for item_id in requested_control_ids]
    for upload in files:
        size = _upload_size(upload)
        evidence = Iso45001EvidenciaDocumental(
            evaluacion=evaluation,
            usuario=user,
            archivo_nombre_original=upload.filename,
            archivo_guardado=store_upload(
                upload,
                f"iso45001/evaluaciones/{evaluation.id}/documentacion",
            ),
            mime_type=upload.mimetype or "application/octet-stream",
            tamano_bytes=size,
            activo=True,
        )
        evidence.controles_evidencia = targets
        db.session.add(evidence)
        created.append(evidence)
    db.session.flush()
    return {"ok": True, "count": len(created), "evidences": created}


def list_document_evidences(evaluation: Iso45001Evaluacion) -> list[Iso45001EvidenciaDocumental]:
    """List active reusable documentary files for the exact evaluation only."""

    return [evidence for evidence in evaluation.evidencias_documentales if evidence.activo]


def _upload_size(upload) -> int:
    stream = upload.stream
    position = stream.tell()
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(position)
    return size


def _normalise_optional_text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _completion(answered: int, total: int) -> float:
    return round((answered / total) * 100, 2) if total else 0.0


def _iso45001_numeric_key(value: object) -> tuple:
    """Return a stable numeric sort key for ISO clauses such as ``10.2``."""

    parts = str(value or "").split(".")
    return tuple(int(part) if part.isdigit() else part for part in parts)


def format_iso_datetime(value) -> str:
    local_value = to_localtime(value)
    if local_value is None:
        return "Sin registro"
    return local_value.strftime("%d/%m/%Y %H:%M")


def format_iso45001_datetime(value) -> str:
    """ISO 45001-specific public name used by report builders."""

    return format_iso_datetime(value)
