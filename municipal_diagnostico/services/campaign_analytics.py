from __future__ import annotations

from collections import Counter, defaultdict

from municipal_diagnostico.models import AsignacionCuestionario, CampanaCuestionario
from municipal_diagnostico.services.analytics import (
    SCORE_GUIDE,
    classify_score,
    dominant_distribution_row,
    maturity_distribution,
    priority_bucket,
    recommendation_for_axis,
)
from municipal_diagnostico.timeutils import to_localtime


CAMPAIGN_STATE_LABELS = {
    "borrador": "Borrador",
    "activa": "Activa",
    "cerrada": "Cerrada",
}

ASSIGNMENT_STATE_LABELS = {
    "pendiente": "Pendiente",
    "en_progreso": "En progreso",
    "respondido": "Respondido",
    "cerrado": "Cerrado",
}

FINAL_ASSIGNMENT_STATES = {"respondido", "cerrado"}


def humanize_campaign_state(state: str) -> str:
    return CAMPAIGN_STATE_LABELS.get(state, state.replace("_", " ").capitalize())


def humanize_assignment_state(state: str) -> str:
    return ASSIGNMENT_STATE_LABELS.get(state, state.replace("_", " ").capitalize())


def summarize_assignment(asignacion: AsignacionCuestionario) -> dict:
    cuestionario = asignacion.campana.cuestionario_version
    response_map = {response.reactivo_version_id: response for response in asignacion.respuestas}
    support_map = {support.eje_version_id: support for support in asignacion.soportes}
    axes = []
    total_questions = 0
    answered_questions = 0
    index_score = 0.0

    for eje in cuestionario.ejes:
        reactivos = list(eje.reactivos)
        total_questions += len(reactivos)
        values = []
        answered = 0

        for reactivo in reactivos:
            response = response_map.get(reactivo.id)
            values.append(response.valor if response else 0)
            if response:
                answered += 1

        answered_questions += answered
        average = round(sum(values) / len(reactivos), 2) if reactivos else 0.0
        weighted = round(average * eje.ponderacion, 4)
        gap = round(3 - average, 2)
        priority_label, priority_slug = priority_bucket(average, eje.ponderacion)
        maturity_label, maturity_slug = classify_score(average)
        support = support_map.get(eje.id)
        index_score += weighted
        axes.append(
            {
                "id": eje.id,
                "clave": eje.clave,
                "nombre": eje.nombre,
                "ponderacion": eje.ponderacion,
                "promedio": average,
                "ponderado": weighted,
                "brecha": gap,
                "progreso": round((answered / len(reactivos)) * 100, 2) if reactivos else 0,
                "respondidos": answered,
                "total": len(reactivos),
                "madurez": maturity_label,
                "maturity_slug": maturity_slug,
                "prioridad": priority_label,
                "priority_slug": priority_slug,
                "recomendaciones": recommendation_for_axis(eje.nombre, average),
                "support_comment": support.comentario if support else None,
                "support_file": support.archivo_nombre_original if support else None,
                "support_present": bool(support and (support.comentario or support.archivo_guardado)),
            }
        )

    index_score = round(index_score, 2)
    level_label, level_slug = classify_score(index_score)
    axis_map = {axis["id"]: axis for axis in axes}
    completion = round((answered_questions / total_questions) * 100, 2) if total_questions else 0

    return {
        "axes": axes,
        "axis_map": axis_map,
        "axes_sorted": sorted(axes, key=lambda axis: (-axis["brecha"], -axis["ponderacion"], axis["nombre"])),
        "index_score": index_score,
        "level_label": level_label,
        "level_slug": level_slug,
        "answered_questions": answered_questions,
        "total_questions": total_questions,
        "completion": completion,
        "support_count": len([axis for axis in axes if axis["support_present"]]),
        "state": asignacion.estado,
        "state_label": humanize_assignment_state(asignacion.estado),
        "critical_axes": [axis for axis in axes if axis["priority_slug"] == "critical"],
        "is_preliminary": asignacion.estado not in FINAL_ASSIGNMENT_STATES,
    }


def build_assignment_report_detail(asignacion: AsignacionCuestionario) -> dict:
    summary = summarize_assignment(asignacion)
    cuestionario = asignacion.campana.cuestionario_version
    response_map = {response.reactivo_version_id: response for response in asignacion.respuestas}
    support_map = {support.eje_version_id: support for support in asignacion.soportes}

    axes = []
    for axis in cuestionario.ejes:
        axis_summary = summary["axis_map"][axis.id]
        support = support_map.get(axis.id)
        questions = []

        for reactive in axis.reactivos:
            response = response_map.get(reactive.id)
            selected_value = response.valor if response else None
            questions.append(
                {
                    "id": reactive.id,
                    "codigo": reactive.codigo,
                    "question": reactive.pregunta,
                    "has_response": response is not None,
                    "selected_value": selected_value,
                    "selected_level": f"Nivel {selected_value}" if response else "Sin respuesta",
                    "selected_option": reactive.opciones.get(str(selected_value), "Sin respuesta") if response else "Sin respuesta",
                    "area_name": asignacion.dependencia_visible.nombre if asignacion.dependencia_visible else "Sin dependencia asignada",
                    "comment": response.comentario if response and response.comentario else "Sin comentario",
                    "captured_by": response.usuario.nombre if response and response.usuario else "Sin respondente",
                    "updated_at_label": _format_datetime_label(response.updated_at if response else None),
                    "options": [
                        {
                            "value": option_value,
                            "label": reactive.opciones.get(str(option_value), ""),
                            "selected": selected_value == option_value,
                        }
                        for option_value in range(4)
                    ],
                }
            )

        evidence_rows = []
        if support and support.archivo_guardado:
            evidence_rows.append(
                {
                    "name": support.archivo_nombre_original,
                    "version": 1,
                    "mime_type": support.mime_type or "application/octet-stream",
                    "created_at_label": _format_datetime_label(support.updated_at or support.created_at),
                }
            )

        axes.append(
            {
                "id": axis.id,
                "clave": axis.clave,
                "nombre": axis.nombre,
                "summary": axis_summary,
                "questions": questions,
                "axis_comment": support.comentario if support and support.comentario else "Sin comentario general",
                "axis_comment_area": asignacion.respondente.nombre if asignacion.respondente else asignacion.objetivo_nombre,
                "axis_comment_author": support.usuario.nombre if support and support.usuario else (asignacion.respondente.nombre if asignacion.respondente else "Sin usuario registrado"),
                "axis_comment_updated_at": _format_datetime_label((support.updated_at or support.created_at) if support else None),
                "evidence": evidence_rows,
            }
        )

    return {
        "summary": summary,
        "axes": axes,
        "score_guide": SCORE_GUIDE,
        "questionnaire_name": cuestionario.nombre,
        "total_axes": len(axes),
        "total_evidence": sum(len(axis["evidence"]) for axis in axes),
        "heatmap_rows": [
            {
                "axis_name": axis["nombre"],
                "axis_key": axis["clave"],
                "selected_slug": axis["summary"]["maturity_slug"],
                "selected_label": axis["summary"]["madurez"],
                "average": axis["summary"]["promedio"],
                "gap": axis["summary"]["brecha"],
            }
            for axis in axes
        ],
    }


def visible_assignments(campana: CampanaCuestionario, role: str) -> list[AsignacionCuestionario]:
    assignments = list(campana.asignaciones)
    if role == "consulta":
        return [assignment for assignment in assignments if assignment.estado in FINAL_ASSIGNMENT_STATES]
    return assignments


def summarize_campaign(campana: CampanaCuestionario, role: str = "administrador") -> dict:
    assignments = visible_assignments(campana, role)
    rows = []
    state_counts = {state: 0 for state in ASSIGNMENT_STATE_LABELS}

    for assignment in campana.asignaciones:
        state_counts[assignment.estado] = state_counts.get(assignment.estado, 0) + 1

    for assignment in assignments:
        summary = summarize_assignment(assignment)
        rows.append(
            {
                "asignacion": assignment,
                "summary": summary,
                "target_name": assignment.objetivo_nombre,
                "target_type": assignment.target_type,
                "dependencia": assignment.dependencia_visible.nombre if assignment.dependencia_visible else "Sin dependencia",
                "respondente": assignment.respondente.nombre if assignment.respondente else "Sin respondente",
                "estado": assignment.estado,
                "estado_label": summary["state_label"],
                "avance": summary["completion"],
                "indice": summary["index_score"],
                "nivel": summary["level_label"],
                "nivel_slug": summary["level_slug"],
                "ultima_actividad_at": assignment.ultima_actividad_at or assignment.updated_at,
                "support_count": summary["support_count"],
                "is_final": assignment.estado in FINAL_ASSIGNMENT_STATES,
            }
        )

    rows.sort(key=lambda row: (row["avance"], row["indice"], row["target_name"]), reverse=True)
    for position, row in enumerate(rows, start=1):
        row["rank"] = position

    rollup_source = rows if role == "administrador" else [row for row in rows if row["is_final"]]
    if not rollup_source and rows:
        rollup_source = rows

    axis_rollup = []
    by_dependency_bucket: dict[str, list[dict]] = defaultdict(list)
    by_user_bucket: dict[str, list[dict]] = defaultdict(list)

    for row in rows:
        by_dependency_bucket[row["dependencia"]].append(row)
        by_user_bucket[row["respondente"]].append(row)

    for eje in campana.cuestionario_version.ejes:
        axis_entries = []
        for row in rollup_source:
            axis = row["summary"]["axis_map"][eje.id]
            axis_entries.append(axis)

        if not axis_entries:
            continue

        average = round(sum(item["promedio"] for item in axis_entries) / len(axis_entries), 2)
        gap_average = round(sum(item["brecha"] for item in axis_entries) / len(axis_entries), 2)
        level_label, level_slug = classify_score(average)
        distribution = maturity_distribution(
            Counter(item["maturity_slug"] for item in axis_entries),
            len(axis_entries),
        )
        axis_rollup.append(
            {
                "axis_id": eje.id,
                "clave": eje.clave,
                "nombre": eje.nombre,
                "promedio": average,
                "brecha_promedio": gap_average,
                "level_label": level_label,
                "level_slug": level_slug,
                "distribution": distribution,
                "dominant_level": dominant_distribution_row(distribution),
                "recommendations": recommendation_for_axis(eje.nombre, average),
                "assignments": len(axis_entries),
            }
        )

    axis_rollup.sort(key=lambda item: (item["brecha_promedio"], item["nombre"]), reverse=True)

    dependency_rows = []
    for dependency_name, dependency_items in by_dependency_bucket.items():
        avg_progress = round(sum(item["avance"] for item in dependency_items) / len(dependency_items), 2)
        avg_index = round(sum(item["indice"] for item in dependency_items) / len(dependency_items), 2)
        dependency_rows.append(
            {
                "dependencia": dependency_name,
                "total": len(dependency_items),
                "respondidas": len([item for item in dependency_items if item["is_final"]]),
                "avance_promedio": avg_progress,
                "indice_promedio": avg_index,
            }
        )
    dependency_rows.sort(key=lambda item: (item["avance_promedio"], item["indice_promedio"], item["dependencia"]), reverse=True)

    user_rows = []
    for user_name, user_items in by_user_bucket.items():
        avg_progress = round(sum(item["avance"] for item in user_items) / len(user_items), 2)
        avg_index = round(sum(item["indice"] for item in user_items) / len(user_items), 2)
        user_rows.append(
            {
                "usuario": user_name,
                "total": len(user_items),
                "respondidas": len([item for item in user_items if item["is_final"]]),
                "avance_promedio": avg_progress,
                "indice_promedio": avg_index,
                "acciones_pendientes": len([item for item in user_items if not item["is_final"]]),
            }
        )
    user_rows.sort(key=lambda item: (item["avance_promedio"], item["indice_promedio"], item["usuario"]), reverse=True)

    total_assignments = len(campana.asignaciones)
    visible_total = len(rows)
    completed = len([row for row in rows if row["is_final"]])
    avg_completion = round(sum(row["avance"] for row in rows) / visible_total, 2) if visible_total else 0

    return {
        "rows": rows,
        "state_counts": state_counts,
        "axis_rollup": axis_rollup,
        "dependency_rows": dependency_rows,
        "user_rows": user_rows,
        "total_assignments": total_assignments,
        "visible_total": visible_total,
        "completed_count": completed,
        "avg_completion": avg_completion,
        "role": role,
        "campaign_state_label": humanize_campaign_state(campana.estado),
    }


def _format_datetime_label(value) -> str:
    local_value = to_localtime(value)
    if local_value is None:
        return "Sin registro"
    return local_value.strftime("%d/%m/%Y %H:%M")
