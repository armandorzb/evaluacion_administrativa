from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import uuid

from flask import current_app

from municipal_diagnostico.extensions import db
from municipal_diagnostico.iso45001_seed_data import (
    ISO45001_V2_VERSION,
    ISO45001_V3_CATALOG_SLUG,
    ISO45001_V3_VERSION,
    ISO45001_VERSION,
)
from municipal_diagnostico.models import (
    Iso45001Apartado,
    Iso45001Clausula,
    Iso45001ControlEvidencia,
    Iso45001ControlEvidenciaPunto,
    Iso45001ControlEvidenciaPuntoReactivo,
    Iso45001ControlEvidenciaReactivo,
    Iso45001CuestionarioVersion,
    Iso45001CambioCaptura,
    Iso45001DocumentoRequerido,
    Iso45001EvidenciaDocumental,
    Iso45001EvaluacionSnapshotCierre,
    Iso45001EvaluacionControlEvidencia,
    Iso45001EvaluacionControlEvidenciaPunto,
    Iso45001Evaluacion,
    Iso45001Reactivo,
    Iso45001ReactivoCrosswalk,
    Iso45001Respuesta,
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
    """Seed immutable ISO 45001 catalogs and return adaptive-capture v3.

    V1 and v2 remain queryable so their reports retain their original evidence
    semantics.  When v3 is first published, cycles without any user capture may
    be safely retargeted because every R-code has a one-to-one crosswalk.
    """

    _ensure_iso45001_catalog_version(ISO45001_VERSION)
    _ensure_iso45001_catalog_version(ISO45001_V2_VERSION)
    version = _ensure_iso45001_catalog_version(ISO45001_V3_VERSION)
    # The deployment has no captured questionnaires.  Keep this idempotent
    # guard enabled so any untouched cycle left by a partially completed
    # deployment is moved to v3, while a cycle with even one user datum remains
    # pinned to its original immutable catalog.
    _retarget_empty_iso45001_cycles(version)
    return version


def _ensure_iso45001_catalog_version(payload: dict) -> Iso45001CuestionarioVersion:
    version = Iso45001CuestionarioVersion.query.filter_by(slug=payload["slug"]).first()
    if version is not None:
        stored_hash = getattr(version, "catalog_hash", None)
        expected_hash = payload.get("catalog_hash")
        if stored_hash and expected_hash and stored_hash != expected_hash:
            raise RuntimeError(
                f"El catálogo ISO 45001 {version.slug} no coincide con su huella publicada. "
                "Crea una versión nueva en lugar de modificar una versión existente."
            )
        metadata_changed = False
        for field in (
            "capture_mode",
            "document_coverage_mode",
            "scoring_scheme",
            "catalog_hash",
        ):
            expected = payload.get(field)
            if expected is not None and getattr(version, field, None) != expected:
                setattr(version, field, expected)
                metadata_changed = True
        if metadata_changed:
            db.session.commit()
        return version

    version = Iso45001CuestionarioVersion(
        slug=payload["slug"],
        nombre=payload["nombre"],
        descripcion=payload["descripcion"],
        norma=payload["norma"],
        capture_mode=payload.get("capture_mode", "individual"),
        document_coverage_mode=payload.get("document_coverage_mode", "por_reactivo"),
        scoring_scheme=payload.get("scoring_scheme", "escala_0_1_2_v1"),
        catalog_hash=payload.get("catalog_hash"),
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
                    variable_principal=reactive_payload.get("variable_principal"),
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
            point = Iso45001ControlEvidenciaPunto(
                control=control,
                orden=point_payload["orden"],
                texto=point_payload["texto"],
            )
            db.session.add(point)
            db.session.flush()
            for reactive_code in point_payload.get("reactivos", []):
                reactive = reactives_by_code.get(reactive_code)
                if reactive is None:
                    raise ValueError(
                        f"El punto {control.codigo}.P{point.orden} referencia el reactivo "
                        f"inexistente {reactive_code}."
                    )
                db.session.add(
                    Iso45001ControlEvidenciaPuntoReactivo(
                        punto=point,
                        reactivo=reactive,
                    )
                )
        for reactive_code in control_payload.get("reactivos", []):
            reactive = reactives_by_code.get(reactive_code)
            if reactive is None:
                raise ValueError(
                    f"El control ISO 45001 {control.codigo} referencia el reactivo inexistente {reactive_code}."
                )
            db.session.add(Iso45001ControlEvidenciaReactivo(control=control, reactivo=reactive))

    for crosswalk_payload in payload.get("crosswalk_reactivos", []):
        source_slug = crosswalk_payload["origen_slug"]
        destination_slug = crosswalk_payload.get("destino_slug", version.slug)
        source_version = Iso45001CuestionarioVersion.query.filter_by(slug=source_slug).one()
        destination_version = (
            version
            if destination_slug == version.slug
            else Iso45001CuestionarioVersion.query.filter_by(slug=destination_slug).one()
        )
        source_reactives = {
            reactive.codigo: reactive
            for clause in source_version.clausulas
            for section in clause.apartados
            for reactive in section.reactivos
        }
        destination_reactives = (
            reactives_by_code
            if destination_version.id == version.id
            else {
                reactive.codigo: reactive
                for clause in destination_version.clausulas
                for section in clause.apartados
                for reactive in section.reactivos
            }
        )
        source = source_reactives.get(crosswalk_payload["origen_codigo"])
        destination = destination_reactives.get(crosswalk_payload["destino_codigo"])
        if source is None or destination is None:
            raise ValueError("El crosswalk ISO 45001 referencia un reactivo inexistente.")
        db.session.add(
            Iso45001ReactivoCrosswalk(
                version_origen=source_version,
                reactivo_origen=source,
                version_destino=destination_version,
                reactivo_destino=destination,
                tipo=crosswalk_payload.get("tipo", "equivalente"),
            )
        )

    db.session.commit()
    return version


def _retarget_empty_iso45001_cycles(version: Iso45001CuestionarioVersion) -> int:
    """Move only completely untouched cycles to v3 on its first publication."""

    moved = 0
    cycles = {
        cycle.id: cycle
        for catalog in Iso45001CuestionarioVersion.query.filter(
            Iso45001CuestionarioVersion.id != version.id
        ).all()
        for cycle in catalog.ciclos
    }
    for cycle in cycles.values():
        if any(_iso45001_evaluation_has_user_capture(item) for item in cycle.evaluaciones):
            continue
        cycle.version = version
        for evaluation in cycle.evaluaciones:
            for assessment in list(evaluation.controles_evidencia):
                db.session.delete(assessment)
            db.session.flush()
            ensure_document_controls_for_evaluation(evaluation)
        moved += 1
    if moved:
        db.session.commit()
    return moved


def _iso45001_evaluation_has_user_capture(evaluation: Iso45001Evaluacion) -> bool:
    if evaluation.respuestas or evaluation.observaciones:
        return True
    if any(evidence.activo for evidence in evaluation.evidencias_documentales):
        return True
    return any(
        assessment.observacion
        or any(evidence.activo for evidence in assessment.archivos)
        or any(
            getattr(point, "evaluado", False)
            or point.cubierto
            or point.observacion
            for point in assessment.puntos
        )
        for assessment in evaluation.controles_evidencia
    )


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

    configured_mode = getattr(version, "document_coverage_mode", None) or "por_reactivo"
    return configured_mode in {"por_control", "por_control_punto"}


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
    points_created = False
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
                points_created = True

    if created or points_created:
        db.session.flush()
    return [existing[control.id] for control in controls]


def record_iso45001_capture_change(
    evaluation: Iso45001Evaluacion,
    *,
    reactive=None,
    point_response=None,
    previous,
    current,
    origin,
    batch_id=None,
    user,
):
    """Append one immutable audit event for a capture value change."""

    if reactive is None and point_response is None:
        raise ValueError("El evento de captura debe identificar un reactivo o un punto documental.")
    if reactive is not None and point_response is not None:
        raise ValueError("El evento de captura no puede identificar dos entidades a la vez.")
    if origin not in {"individual", "masivo", "excepcion"}:
        raise ValueError("El origen de captura no es válido.")
    if user is None or getattr(user, "id", None) is None:
        raise ValueError("El evento de captura requiere un usuario persistido.")
    if previous == current:
        return None

    if point_response is not None and getattr(point_response, "id", None) is None:
        db.session.flush()
    event = Iso45001CambioCaptura(
        evaluacion=evaluation,
        entidad_tipo="reactivo" if reactive is not None else "punto_documental",
        entidad_id=(reactive.id if reactive is not None else point_response.id),
        reactivo=reactive,
        punto=point_response,
        valor_anterior=previous,
        valor_nuevo=current,
        origen=origin,
        lote_id=batch_id,
        usuario=user,
    )
    db.session.add(event)
    return event


def bulk_apply_section_responses(
    evaluation: Iso45001Evaluacion,
    section_id: int,
    calificacion: str,
    mode: str = "pendientes",
    *,
    user=None,
) -> dict:
    """Apply one score to pending or all reactives in a catalog section."""

    if calificacion not in ISO45001_OPTION_POINTS:
        return {"ok": False, "error": "La calificación debe ser No, Parcial o Sí."}
    if mode not in {"pendientes", "reemplazar"}:
        return {"ok": False, "error": "El modo debe ser pendientes o reemplazar."}

    section = next(
        (
            section
            for clause in evaluation.ciclo.version.clausulas
            for section in clause.apartados
            if section.id == int(section_id)
        ),
        None,
    )
    if section is None:
        return {"ok": False, "error": "El apartado no pertenece a esta evaluación."}

    batch_id = str(uuid.uuid4())
    response_map = {response.reactivo_id: response for response in evaluation.respuestas}
    updated = 0
    skipped = 0
    for reactive in section.reactivos:
        response = response_map.get(reactive.id)
        if mode == "pendientes" and response is not None and response.calificacion in ISO45001_OPTION_POINTS:
            skipped += 1
            continue

        previous = (
            {
                "calificacion": response.calificacion,
                "valor": response.valor,
                "observacion": response.observacion,
                "origen": getattr(response, "origen_captura", None) or "individual",
                "lote": getattr(response, "lote_captura", None),
            }
            if response is not None
            else None
        )
        if response is None:
            response = Iso45001Respuesta(
                evaluacion=evaluation,
                reactivo=reactive,
                usuario=user,
                calificacion=calificacion,
            )
            db.session.add(response)
            response_map[reactive.id] = response
        response.calificacion = calificacion
        response.valor = ISO45001_OPTION_POINTS[calificacion]
        response.usuario = user
        response.origen_captura = "masivo"
        response.lote_captura = batch_id
        current = {
            "calificacion": response.calificacion,
            "valor": response.valor,
            "observacion": response.observacion,
            "origen": "masivo",
            "lote": batch_id,
        }
        record_iso45001_capture_change(
            evaluation,
            reactive=reactive,
            previous=previous,
            current=current,
            origin="masivo",
            batch_id=batch_id,
            user=user,
        )
        updated += 1

    db.session.flush()
    return {
        "ok": True,
        "updated": updated,
        "skipped": skipped,
        "batch_id": batch_id,
    }


def bulk_apply_document_control_points(
    evaluation: Iso45001Evaluacion,
    control_id: int,
    covered: bool,
    mode: str = "pendientes",
    *,
    user=None,
) -> dict:
    """Apply documentary coverage to pending or all points of one control."""

    if getattr(evaluation.ciclo.version, "document_coverage_mode", None) != "por_control_punto":
        return {"ok": False, "error": "Esta versión no habilita cobertura documental por punto."}
    if mode not in {"pendientes", "reemplazar"}:
        return {"ok": False, "error": "El modo debe ser pendientes o reemplazar."}
    if not isinstance(covered, bool):
        return {"ok": False, "error": "La cobertura debe ser verdadera o falsa."}

    assessments = ensure_document_controls_for_evaluation(evaluation, user=user)
    assessment = next((item for item in assessments if item.id == int(control_id)), None)
    if assessment is None:
        return {"ok": False, "error": "El control documental no pertenece a esta evaluación."}

    batch_id = str(uuid.uuid4())
    updated = 0
    skipped = 0
    for response in assessment.puntos:
        if mode == "pendientes" and getattr(response, "evaluado", False):
            skipped += 1
            continue
        previous = {
            "cubierto": bool(response.cubierto),
            "evaluado": bool(getattr(response, "evaluado", False)),
            "observacion": response.observacion,
            "origen": getattr(response, "origen_captura", None) or "individual",
            "lote": getattr(response, "lote_captura", None),
        }
        response.cubierto = covered
        response.evaluado = True
        if not covered:
            response.archivos = []
        response.origen_captura = "masivo"
        response.lote_captura = batch_id
        current = {
            "cubierto": covered,
            "evaluado": True,
            "observacion": response.observacion,
            "origen": "masivo",
            "lote": batch_id,
        }
        record_iso45001_capture_change(
            evaluation,
            point_response=response,
            previous=previous,
            current=current,
            origin="masivo",
            batch_id=batch_id,
            user=user,
        )
        updated += 1

    assessment.estado = _document_control_state(
        sum(bool(response.cubierto) for response in assessment.puntos),
        len(assessment.puntos),
    )
    assessment.usuario = user
    db.session.flush()
    return {
        "ok": True,
        "updated": updated,
        "skipped": skipped,
        "batch_id": batch_id,
    }


def summarize_iso45001_evaluation(evaluation: Iso45001Evaluacion) -> dict:
    """Build the canonical reporting view of an ISO 45001 evaluation.

    Every catalog reactive is applicable.  Therefore capture completion and
    compliance are intentionally independent: compliance always uses the full
    possible score, while completion reflects how much has been answered.
    """

    snapshot = getattr(evaluation, "snapshot_cierre", None)
    if (
        evaluation.estado in ISO45001_FINAL_STATES
        and snapshot is not None
        and (getattr(evaluation.ciclo.version, "capture_mode", None) or "individual")
        != "individual"
    ):
        return _summary_from_iso45001_snapshot(evaluation, snapshot)

    version = evaluation.ciclo.version
    has_document_controls = uses_document_control_coverage(version)
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
    dimension_totals: dict[str, dict] = {}

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

                dimension_name = (
                    getattr(reactive, "variable_principal", None)
                    or section.nombre
                    or section.codigo
                )
                dimension = dimension_totals.setdefault(
                    dimension_name,
                    {
                        "variable_principal": dimension_name,
                        "total": 0,
                        "answered": 0,
                        "points": 0,
                        "maximum_points": 0,
                    },
                )
                dimension["total"] += 1
                dimension["answered"] += int(row["answered"])
                dimension["points"] += row["points"]
                dimension["maximum_points"] += 2

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
    completion = _completion(answered_questions, total_questions)
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
        "completion": completion,
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
        "dimensions": [
            {
                **dimension,
                "completion": _completion(dimension["answered"], dimension["total"]),
                "percent": score_percent(dimension["points"], dimension["total"]),
            }
            for dimension in dimension_totals.values()
        ],
        "catalog_version": version.slug,
        "catalog_hash": getattr(version, "catalog_hash", None),
        "scoring_scheme": getattr(version, "scoring_scheme", None) or "escala_0_1_2_v1",
        "capture_mode": getattr(version, "capture_mode", None) or "individual",
        "document_coverage_mode": (
            getattr(version, "document_coverage_mode", None) or "por_reactivo"
        ),
        "uses_adaptive_capture": (
            (getattr(version, "capture_mode", None) or "individual") != "individual"
        ),
        "catalog_metadata": {
            "version_name": version.nombre,
            "version_slug": version.slug,
            "catalog_hash": getattr(version, "catalog_hash", None),
            "capture_mode": getattr(version, "capture_mode", None) or "individual",
            "document_coverage_mode": (
                getattr(version, "document_coverage_mode", None) or "por_reactivo"
            ),
            "scoring_scheme": (
                getattr(version, "scoring_scheme", None) or "escala_0_1_2_v1"
            ),
        },
        "capture_traceability": list(evaluation.cambios_captura),
        "is_final": evaluation.estado in ISO45001_FINAL_STATES,
    }


def freeze_iso45001_snapshot(evaluation: Iso45001Evaluacion, *, user):
    """Create the one immutable reporting source used after a v3 closure."""

    if (getattr(evaluation.ciclo.version, "capture_mode", None) or "individual") == "individual":
        return None
    existing = getattr(evaluation, "snapshot_cierre", None)
    if existing is not None:
        return existing
    if user is None or getattr(user, "id", None) is None:
        raise ValueError("El snapshot de cierre requiere un usuario persistido.")

    summary = summarize_iso45001_evaluation(evaluation)
    version = evaluation.ciclo.version
    report_summary = _freeze_iso45001_report_summary(summary)
    content = {
        "schema_version": "iso45001-cierre-v1",
        "evaluation": {
            "id": evaluation.id,
            "estado": evaluation.estado,
            "ciclo": evaluation.ciclo.nombre,
            "dependencia": evaluation.dependencia.nombre,
            "area": evaluation.area.nombre if evaluation.area else None,
            "cerrada_at": _snapshot_datetime(evaluation.cerrada_at),
        },
        "catalog": report_summary["catalog_metadata"],
        "formula": {
            "scheme": report_summary["scoring_scheme"],
            "values": {"no": 0, "parcial": 1, "si": 2},
            "maximum_points": report_summary["maximum_points"],
        },
        "report_summary": report_summary,
    }
    canonical = _canonical_snapshot_json(content)
    content_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    catalog_hash = getattr(version, "catalog_hash", None)
    if not catalog_hash:
        catalog_hash = hashlib.sha256(
            _canonical_snapshot_json(report_summary["catalog_metadata"]).encode("utf-8")
        ).hexdigest()
    snapshot = Iso45001EvaluacionSnapshotCierre(
        evaluacion=evaluation,
        version=version,
        usuario=user,
        catalog_slug=version.slug,
        catalog_hash=catalog_hash,
        scoring_scheme=getattr(version, "scoring_scheme", None) or "escala_0_1_2_v1",
        contenido=content,
        contenido_sha256=content_hash,
    )
    db.session.add(snapshot)
    db.session.flush()
    return snapshot


def _freeze_iso45001_report_summary(summary: dict) -> dict:
    frozen_sections: list[dict] = []
    frozen_clauses: list[dict] = []
    for clause in summary["clauses"]:
        clause_copy = {
            key: value
            for key, value in clause.items()
            if key not in {"sections"} and _is_snapshot_scalar_tree(value)
        }
        clause_sections = []
        for section in clause["sections"]:
            section_copy = {
                key: value
                for key, value in section.items()
                if key not in {"questions"} and _is_snapshot_scalar_tree(value)
            }
            section_copy["questions"] = [
                _freeze_iso45001_question(row) for row in section["questions"]
            ]
            clause_sections.append(section_copy)
            frozen_sections.append(section_copy)
        clause_copy["sections"] = clause_sections
        frozen_clauses.append(clause_copy)

    frozen_controls = [
        _freeze_iso45001_document_control(control)
        for control in summary.get("document_controls", [])
    ]
    catalog_metadata = dict(summary.get("catalog_metadata") or {})
    catalog_metadata.setdefault("version_slug", summary.get("catalog_version"))
    catalog_metadata.setdefault("catalog_hash", summary.get("catalog_hash"))
    catalog_metadata.setdefault("capture_mode", summary.get("capture_mode"))
    catalog_metadata.setdefault(
        "document_coverage_mode", summary.get("document_coverage_mode")
    )
    catalog_metadata.setdefault("scoring_scheme", summary.get("scoring_scheme"))

    return {
        "total_questions": summary["total_questions"],
        "answered_questions": summary["answered_questions"],
        "applicable_questions": summary["applicable_questions"],
        "na_questions": summary["na_questions"],
        "points": summary["points"],
        "maximum_points": summary["maximum_points"],
        "completion": summary["completion"],
        "percent": summary["percent"],
        "maturity_label": summary["maturity_label"],
        "maturity_slug": summary["maturity_slug"],
        "state_label": summary["state_label"],
        "evidence_count": summary["evidence_count"],
        "reactive_evidence_count": summary["reactive_evidence_count"],
        "evidence_coverage": summary["evidence_coverage"],
        "document_evidence_stats": summary["document_evidence_stats"],
        "response_counts": summary["response_counts"],
        "dimensions": summary.get("dimensions", []),
        "clauses": frozen_clauses,
        "sections": frozen_sections,
        "document_controls": frozen_controls,
        "uses_document_control_coverage": summary["uses_document_control_coverage"],
        "uses_adaptive_capture": summary.get("uses_adaptive_capture", False),
        "catalog_version": summary.get("catalog_version"),
        "catalog_hash": summary.get("catalog_hash"),
        "scoring_scheme": summary.get("scoring_scheme"),
        "capture_mode": summary.get("capture_mode"),
        "document_coverage_mode": summary.get("document_coverage_mode"),
        "catalog_metadata": catalog_metadata,
        "capture_traceability": [
            _freeze_iso45001_capture_event(event)
            for event in summary.get("capture_traceability", [])
        ],
        "is_final": True,
    }


def _freeze_iso45001_question(row: dict) -> dict:
    reactive = row["reactivo"]
    documents = [
        {
            "id": document.id,
            "codigo": document.codigo,
            "nombre": document.nombre,
            "apartado": document.apartado,
            "clasificacion": document.clasificacion,
            "criticidad": document.criticidad,
        }
        for document in row.get("documents", [])
    ]
    controls = [
        {
            "id": control.id,
            "codigo": control.codigo,
            "nombre": control.nombre,
            "apartado": control.apartado,
            "clausula": control.clausula,
        }
        for control in getattr(reactive, "controles_evidencia", ())
    ]
    evidence = [
        {
            "id": item.id,
            "archivo_nombre_original": item.archivo_nombre_original,
            "archivo_guardado": item.archivo_guardado,
            "mime_type": item.mime_type,
            "tamano_bytes": item.tamano_bytes,
            "sha256": getattr(item, "sha256", None),
            "created_at": _snapshot_datetime(item.created_at),
        }
        for item in row.get("evidence", [])
    ]
    return {
        "reactivo": {
            "id": reactive.id,
            "codigo": reactive.codigo,
            "numero": reactive.numero,
            "orden": reactive.orden,
            "tema": reactive.tema,
            "variable_principal": getattr(reactive, "variable_principal", None),
            "texto": reactive.texto,
            "evidencia_sugerida": reactive.evidencia_sugerida,
            "criterio_idoneidad": reactive.criterio_idoneidad,
            "criticidad": reactive.criticidad,
            "es_enmienda_2024": reactive.es_enmienda_2024,
            "requiere_documento": reactive.requiere_documento,
            "documentos_requeridos": documents,
            "controles_evidencia": controls,
        },
        "answered": row["answered"],
        "selected": row["selected"],
        "selected_label": row["selected_label"],
        "is_na": row["is_na"],
        "applicable": row["applicable"],
        "points": row["points"],
        "observacion": row.get("observacion") or "",
        "capture_origin": row.get("capture_origin"),
        "capture_batch_id": row.get("capture_batch_id"),
        "capture_user": _snapshot_actor(row.get("capture_user")),
        "capture_at": _snapshot_datetime(row.get("capture_at")),
        "evidence": evidence,
        "documents": documents,
        "documentos_requeridos": documents,
        "has_document_requirement": row["has_document_requirement"],
        "requires_evidence": row["requires_evidence"],
        "evidence_satisfied": row["evidence_satisfied"],
        "clausula": row.get("clausula"),
        "apartado": row.get("apartado"),
        "apartado_nombre": row.get("apartado_nombre"),
    }


def _freeze_iso45001_document_control(control: dict) -> dict:
    scalar_keys = {
        "id",
        "catalog_control_id",
        "codigo",
        "categoria",
        "tipo",
        "clausula",
        "apartado",
        "clasificacion",
        "nombre",
        "descripcion",
        "contenido_minimo",
        "evidencia_sugerida",
        "criticidad",
        "orden",
        "estado",
        "estado_label",
        "observacion",
        "evaluated",
        "puntos_cubiertos",
        "total_puntos",
        "coverage_percent",
        "evidence_ids",
        "files_count",
        "requires_file",
    }
    frozen = {key: control.get(key) for key in scalar_keys}
    frozen["reactivos"] = [dict(item) for item in control.get("reactivos", [])]
    frozen["evidencias"] = [
        _freeze_document_evidence_view(item) for item in control.get("evidencias", [])
    ]
    frozen["puntos"] = []
    for point in control.get("puntos", []):
        frozen["puntos"].append(
            {
                key: (
                    [_freeze_document_evidence_view(item) for item in value]
                    if key == "evidencias"
                    else [dict(item) for item in value]
                    if key == "reactivos"
                    else value
                )
                for key, value in point.items()
                if key
                in {
                    "id",
                    "response_id",
                    "orden",
                    "texto",
                    "cubierto",
                    "evaluado",
                    "observacion",
                    "origen_captura",
                    "lote_captura",
                    "reactivos",
                    "evidencias",
                    "evidence_ids",
                }
            }
        )
    return frozen


def _freeze_document_evidence_view(item: dict) -> dict:
    frozen = dict(item)
    frozen["created_at"] = _snapshot_datetime(frozen.get("created_at"))
    return frozen


def _freeze_iso45001_capture_event(event) -> dict:
    reactive = getattr(event, "reactivo", None)
    point_response = getattr(event, "punto", None)
    catalog_point = getattr(point_response, "punto", None) if point_response else None
    control = getattr(catalog_point, "control", None) if catalog_point else None
    return {
        "id": event.id,
        "entidad_tipo": event.entidad_tipo,
        "entidad_id": event.entidad_id,
        "reactivo_id": event.reactivo_id,
        "reactivo_codigo": getattr(reactive, "codigo", None),
        "punto_id": event.punto_id,
        "punto_orden": getattr(catalog_point, "orden", None),
        "control_codigo": getattr(control, "codigo", None),
        "clausula": (
            reactive.apartado.clausula.numero if reactive is not None else getattr(control, "clausula", None)
        ),
        "apartado": (
            reactive.apartado.codigo if reactive is not None else getattr(control, "apartado", None)
        ),
        "variable_principal": getattr(reactive, "variable_principal", None),
        "valor_anterior": event.valor_anterior,
        "valor_nuevo": event.valor_nuevo,
        "origen": event.origen,
        "lote_id": event.lote_id,
        "usuario": _snapshot_actor(event.usuario),
        "created_at": _snapshot_datetime(event.created_at),
    }


def _summary_from_iso45001_snapshot(evaluation, snapshot) -> dict:
    content = snapshot.contenido
    expected = hashlib.sha256(_canonical_snapshot_json(content).encode("utf-8")).hexdigest()
    if expected != snapshot.contenido_sha256:
        raise RuntimeError("El snapshot oficial ISO 45001 no supera la verificación de integridad.")
    frozen = content.get("report_summary")
    if not isinstance(frozen, dict):
        raise RuntimeError("El snapshot oficial ISO 45001 no contiene el resumen de reporte.")

    clauses = []
    flat_sections = []
    findings = []
    for frozen_clause in frozen.get("clauses", []):
        clause = {key: value for key, value in frozen_clause.items() if key != "sections"}
        clause["sections"] = []
        for frozen_section in frozen_clause.get("sections", []):
            section = {key: value for key, value in frozen_section.items() if key != "questions"}
            section["questions"] = []
            for frozen_row in frozen_section.get("questions", []):
                row = dict(frozen_row)
                reactive_data = dict(row["reactivo"])
                documents = [SimpleNamespace(**item) for item in reactive_data.pop("documentos_requeridos", [])]
                controls = [SimpleNamespace(**item) for item in reactive_data.pop("controles_evidencia", [])]
                reactive = SimpleNamespace(
                    **reactive_data,
                    documentos_requeridos=documents,
                    controles_evidencia=controls,
                    apartado=SimpleNamespace(
                        codigo=row.get("apartado"),
                        nombre=row.get("apartado_nombre"),
                        clausula=SimpleNamespace(numero=row.get("clausula")),
                    ),
                )
                row["reactivo"] = reactive
                row["documents"] = documents
                row["documentos_requeridos"] = documents
                row["evidence"] = [SimpleNamespace(**item) for item in row.get("evidence", [])]
                row["finding"] = _finding_for_question(
                    reactive,
                    row.get("selected"),
                    SimpleNamespace(observacion=row.get("observacion")),
                    documents,
                )
                if row["finding"] is not None:
                    findings.append(row["finding"])
                section["questions"].append(row)
            clause["sections"].append(section)
            flat_sections.append(section)
        clauses.append(clause)

    controls = [dict(control) for control in frozen.get("document_controls", [])]
    result = dict(frozen)
    result.update(
        {
            "evaluation": evaluation,
            "clauses": clauses,
            "sections": flat_sections,
            "findings": findings,
            "document_controls": controls,
            "document_requirements": [],
            "documents": [],
            "document_validation": _document_control_validation(controls),
            "capture_traceability": list(frozen.get("capture_traceability", [])),
            "generated_from_snapshot": True,
            "snapshot_hash": snapshot.contenido_sha256,
            "is_final": True,
        }
    )
    return result


def _canonical_snapshot_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _snapshot_datetime(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _snapshot_actor(value):
    if value is None:
        return None
    return getattr(value, "nombre", None) or getattr(value, "email", None) or str(value)


def _is_snapshot_scalar_tree(value) -> bool:
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_snapshot_scalar_tree(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return all(_is_snapshot_scalar_tree(item) for item in value)
    return False


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
                "unidad": evaluation.unidad_administrativa_nombre,
                "alcance": evaluation.alcance_descripcion,
                "es_alcance_legacy": evaluation.area_id is None,
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
    rows.sort(
        key=lambda row: (
            row["dependencia"].casefold(),
            row["unidad"].casefold(),
            -row["avance"],
        )
    )
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
        "capture_origin": getattr(response, "origen_captura", None) or "individual",
        "capture_batch_id": getattr(response, "lote_captura", None),
        "capture_user": getattr(response, "usuario", None) if response else None,
        "capture_at": getattr(response, "updated_at", None) if response else None,
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
    """Return the documentary control view without materializing missing rows."""

    if not uses_document_control_coverage(evaluation.ciclo.version):
        return []

    assessments = list(evaluation.controles_evidencia)
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
            point_evidences = [
                evidence
                for evidence in (getattr(point_response, "archivos", ()) if point_response else ())
                if evidence.activo
            ]
            points.append(
                {
                    "id": point.id,
                    "response_id": point_response.id if point_response else None,
                    "orden": point.orden,
                    "texto": point.texto,
                    "cubierto": bool(point_response and point_response.cubierto),
                    "evaluado": bool(point_response and getattr(point_response, "evaluado", False)),
                    "observacion": point_response.observacion if point_response else "",
                    "origen_captura": (
                        getattr(point_response, "origen_captura", None) or "individual"
                        if point_response
                        else None
                    ),
                    "lote_captura": getattr(point_response, "lote_captura", None) if point_response else None,
                    "reactivos": [
                        {
                            "id": reactive.id,
                            "codigo": reactive.codigo,
                            "apartado": reactive.apartado.codigo,
                            "variable_principal": getattr(reactive, "variable_principal", None),
                            "texto": reactive.texto,
                        }
                        for reactive in getattr(point, "reactivos", ())
                    ],
                    "evidencias": [_document_evidence_view(evidence) for evidence in point_evidences],
                    "evidence_ids": [evidence.id for evidence in point_evidences],
                }
            )
        covered_points = sum(1 for point in points if point["cubierto"])
        total_points = len(points)
        state = _document_control_state(covered_points, total_points)
        evidences = [evidence for evidence in assessment.archivos if evidence.activo]
        observation = _normalise_optional_text(assessment.observacion)
        point_level_mode = (
            getattr(evaluation.ciclo.version, "document_coverage_mode", None)
            == "por_control_punto"
        )
        evaluated = (
            bool(points) and all(point["evaluado"] for point in points)
            if point_level_mode
            else bool(covered_points or evidences or observation)
        )
        missing_evidence_points = [
            point
            for point in points
            if point_level_mode
            and point["evaluado"]
            and point["cubierto"]
            and not point["evidence_ids"]
        ]
        evidence_views = []
        for evidence in evidences:
            view = _document_evidence_view(evidence)
            view["point_ids"] = [
                point_response.control_evidencia_punto_id
                for point_response in getattr(evidence, "puntos", ())
                if point_response.evaluacion_control_evidencia_id == assessment.id
            ]
            evidence_views.append(view)
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
                "evidencias": evidence_views,
                "evidence_ids": [evidence.id for evidence in evidences],
                "files_count": len(evidences),
                "requires_file": state in {"parcial", "si"},
                "missing_evidence_points": missing_evidence_points,
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
        "sha256": getattr(evidence, "sha256", None),
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
        if control["estado"] in {"parcial", "si"}
        and control["files_count"]
        and not control.get("missing_evidence_points")
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
        "gap_controls": sum(
            control["evaluated"] and control["estado"] == "no" for control in controls
        ),
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
        and (
            bool(control.get("missing_evidence_points"))
            or not control["evidence_ids"]
        )
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
    """Persist point coverage plus exact reusable-file-to-point links."""

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

    evidence_point_pairs = None
    if "evidencia_punto_ids" in payload:
        evidence_point_pairs = set()
        try:
            for raw_value in payload.get("evidencia_punto_ids", []):
                if not str(raw_value).strip():
                    continue
                evidence_id_text, point_id_text = str(raw_value).split(":", 1)
                pair = (int(evidence_id_text), int(point_id_text))
                evidence_point_pairs.add(pair)
        except (TypeError, ValueError):
            return {"ok": False, "error": "La relación entre archivos y puntos no es válida."}
        if any(
            evidence_id not in selected_evidence_ids or point_id not in selected_point_ids
            for evidence_id, point_id in evidence_point_pairs
        ):
            return {
                "ok": False,
                "error": "Cada relación archivo-punto debe pertenecer a los elementos seleccionados.",
            }
    elif getattr(evaluation.ciclo.version, "document_coverage_mode", None) == "por_control_punto":
        # Backwards-compatible API fallback: an older client that selects an
        # evidence and covered points means that the evidence supports all of
        # those points.  New clients always send the explicit pair list.
        evidence_point_pairs = {
            (evidence_id, point_id)
            for evidence_id in selected_evidence_ids
            for point_id in selected_point_ids
        }

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
            db.session.flush()
            responses_by_point[point.id] = response
        previous = {
            "cubierto": bool(response.cubierto),
            "evaluado": bool(getattr(response, "evaluado", False)),
            "observacion": response.observacion,
            "origen": getattr(response, "origen_captura", None) or "individual",
            "lote": getattr(response, "lote_captura", None),
        }
        was_bulk = getattr(response, "origen_captura", None) == "masivo"
        response.cubierto = point.id in selected_point_ids
        response.evaluado = True
        changed_value = previous["cubierto"] != response.cubierto or not previous["evaluado"]
        if changed_value:
            response.origen_captura = "excepcion" if was_bulk else "individual"
            response.lote_captura = None
            current = {
                "cubierto": bool(response.cubierto),
                "evaluado": True,
                "observacion": response.observacion,
                "origen": response.origen_captura,
                "lote": None,
            }
            record_iso45001_capture_change(
                evaluation,
                point_response=response,
                previous=previous,
                current=current,
                origin=response.origen_captura,
                user=user,
            )

        if evidence_point_pairs is not None:
            response.archivos = [
                evidence_by_id[evidence_id]
                for evidence_id in selected_evidence_ids
                if (evidence_id, point.id) in evidence_point_pairs
            ]

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
        stored_path = store_upload(
            upload,
            f"iso45001/evaluaciones/{evaluation.id}/documentacion",
        )
        evidence = Iso45001EvidenciaDocumental(
            evaluacion=evaluation,
            usuario=user,
            archivo_nombre_original=upload.filename,
            archivo_guardado=stored_path,
            mime_type=upload.mimetype or "application/octet-stream",
            tamano_bytes=size,
            sha256=stored_upload_sha256(stored_path),
            activo=True,
        )
        evidence.controles_evidencia = targets
        if getattr(evaluation.ciclo.version, "document_coverage_mode", None) == "por_control_punto":
            evidence.puntos = [
                point_response
                for assessment in targets
                for point_response in assessment.puntos
                if getattr(point_response, "evaluado", False) and point_response.cubierto
            ]
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


def stored_upload_sha256(relative_path: str) -> str:
    """Calculate the immutable SHA-256 fingerprint of one stored upload."""

    upload_root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    stored_path = (upload_root / relative_path).resolve()
    try:
        stored_path.relative_to(upload_root)
    except ValueError as exc:
        raise ValueError("La ruta de evidencia quedó fuera del repositorio de archivos.") from exc
    digest = hashlib.sha256()
    with stored_path.open("rb") as stored_file:
        for chunk in iter(lambda: stored_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
