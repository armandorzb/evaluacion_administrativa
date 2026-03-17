from __future__ import annotations

from collections import Counter

from municipal_diagnostico.models import Evaluacion
from municipal_diagnostico.seed_data import RECOMMENDATION_LIBRARY


OFFICIAL_EVALUATION_STATES = {"aprobada", "cerrada"}
PRELIMINARY_EVALUATION_STATES = {"borrador", "en_captura", "en_revision", "devuelta"}
REPORTABLE_EVALUATION_STATES = OFFICIAL_EVALUATION_STATES | PRELIMINARY_EVALUATION_STATES

STATE_LABELS = {
    "borrador": "Borrador",
    "en_captura": "En captura",
    "en_revision": "En revisión",
    "devuelta": "Devuelta",
    "aprobada": "Aprobada",
    "cerrada": "Cerrada",
}

LEVELS = [
    (1.50, "Bajo", "low"),
    (2.00, "Medio", "medium"),
    (2.50, "Alto", "high"),
    (3.00, "Óptimo", "optimal"),
]

MATURITY_SCALE = [
    ("low", "Bajo"),
    ("medium", "Medio"),
    ("high", "Alto"),
    ("optimal", "Óptimo"),
]

PRIORITY_STYLES = {
    "Crítico": "critical",
    "Prioritario": "priority",
    "Mejorable": "improvable",
    "Oportuno": "opportune",
}


def visible_states_for_role(role: str) -> set[str]:
    return REPORTABLE_EVALUATION_STATES if role == "administrador" else OFFICIAL_EVALUATION_STATES


def select_reporting_period(periods: list, selected_period_id: int | None = None):
    if not periods:
        return None

    if selected_period_id:
        selected = next((period for period in periods if period.id == selected_period_id), None)
        if selected:
            return selected

    preferred = [period for period in periods if period.estado in {"abierto", "reabierto"}]
    return preferred[0] if preferred else periods[0]


def humanize_state(state: str) -> str:
    return STATE_LABELS.get(state, state.replace("_", " ").capitalize())


def classify_score(score: float) -> tuple[str, str]:
    for upper_limit, label, slug in LEVELS:
        if score <= upper_limit:
            return label, slug
    return "Óptimo", "optimal"


def priority_bucket(average: float, weight: float) -> tuple[str, str]:
    impact = weight * 100
    if average <= 1.5 and impact >= 15:
        label = "Crítico"
    elif average <= 2.0 or impact >= 15:
        label = "Prioritario"
    elif average <= 2.5:
        label = "Mejorable"
    else:
        label = "Oportuno"
    return label, PRIORITY_STYLES[label]


def recommendation_for_axis(axis_name: str, average: float) -> list[str]:
    base = RECOMMENDATION_LIBRARY.get(axis_name, [])
    if average <= 1.5:
        return base[:3]
    if average <= 2.0:
        return base[:2]
    if average <= 2.5:
        return base[:1]
    return ["Mantener el estándar actual y documentar evidencia de resultados."]


def maturity_distribution(counts: Counter, total: int) -> list[dict]:
    distribution = []
    for slug, label in MATURITY_SCALE:
        count = counts.get(slug, 0)
        distribution.append(
            {
                "slug": slug,
                "label": label,
                "count": count,
                "percent": round((count / total) * 100, 2) if total else 0,
            }
        )
    return distribution


def dominant_distribution_row(distribution: list[dict]) -> dict:
    if not distribution:
        return {"label": "-", "slug": "low"}
    return max(distribution, key=lambda row: (row["count"], row["percent"]))


def collect_period_evaluation_summaries(periodo, include_states=None) -> list[dict]:
    visible_states = set(include_states or OFFICIAL_EVALUATION_STATES)
    items = []

    for evaluation in periodo.evaluaciones:
        if evaluation.estado not in visible_states:
            continue
        items.append({"evaluacion": evaluation, "summary": summarize_evaluation(evaluation)})
    return items


def summarize_evaluation(evaluacion: Evaluacion) -> dict:
    cuestionario = evaluacion.periodo.cuestionario_version
    response_map = {response.reactivo_version_id: response for response in evaluacion.respuestas}
    axes = []
    total_questions = 0
    answered_questions = 0
    index_score = 0.0

    for eje in cuestionario.ejes:
        reactivos = list(eje.reactivos)
        total_questions += len(reactivos)
        values = []
        answered = 0
        comments = 0
        evidence_count = len(
            [
                evidence
                for evidence in evaluacion.evidencias
                if evidence.eje_version_id == eje.id and evidence.activo
            ]
        )

        for reactivo in reactivos:
            response = response_map.get(reactivo.id)
            value = response.valor if response else 0
            values.append(value)
            if response:
                answered += 1
                if response.comentario:
                    comments += 1

        answered_questions += answered
        average = round(sum(values) / len(reactivos), 2) if reactivos else 0
        weighted = round(average * eje.ponderacion, 4)
        gap = round(3 - average, 2)
        priority_label, priority_slug = priority_bucket(average, eje.ponderacion)
        maturity_label, maturity_slug = classify_score(average)
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
                "comentarios": comments,
                "evidencias": evidence_count,
                "prioridad": priority_label,
                "priority_slug": priority_slug,
                "madurez": maturity_label,
                "maturity_slug": maturity_slug,
                "recomendaciones": recommendation_for_axis(eje.nombre, average),
                "urgencia": round((gap / 3) * 100, 2),
                "impacto": round(eje.ponderacion * 100, 2),
            }
        )

    index_score = round(index_score, 2)
    level_label, level_slug = classify_score(index_score)
    is_preliminary = evaluacion.estado not in OFFICIAL_EVALUATION_STATES
    axes_sorted = sorted(axes, key=lambda axis: (-axis["brecha"], -axis["impacto"], axis["nombre"]))
    axis_map = {axis["id"]: axis for axis in axes}

    return {
        "axes": axes,
        "axes_sorted": axes_sorted,
        "axis_map": axis_map,
        "index_score": index_score,
        "level_label": level_label,
        "level_slug": level_slug,
        "answered_questions": answered_questions,
        "total_questions": total_questions,
        "completion": round((answered_questions / total_questions) * 100, 2) if total_questions else 0,
        "critical_axes": [axis for axis in axes if axis["priority_slug"] == "critical"],
        "is_preliminary": is_preliminary,
        "state": evaluacion.estado,
        "state_label": humanize_state(evaluacion.estado),
        "visible_states": sorted(REPORTABLE_EVALUATION_STATES),
    }


def summarize_period(periodo, include_states=None) -> dict:
    visible_states = set(include_states or OFFICIAL_EVALUATION_STATES)
    visible_items = collect_period_evaluation_summaries(periodo, include_states=visible_states)
    operational_ranking = []
    official_ranking = []
    state_counts = {state: 0 for state in REPORTABLE_EVALUATION_STATES}

    for evaluation in periodo.evaluaciones:
        state_counts[evaluation.estado] = state_counts.get(evaluation.estado, 0) + 1

    for item in visible_items:
        evaluation = item["evaluacion"]
        summary = item["summary"]
        row = {
            "evaluacion": evaluation,
            "dependencia": evaluation.dependencia.nombre,
            "indice": summary["index_score"],
            "nivel": summary["level_label"],
            "nivel_slug": summary["level_slug"],
            "avance": summary["completion"],
            "axes": summary["axes"],
            "estado": evaluation.estado,
            "estado_label": summary["state_label"],
            "is_preliminary": summary["is_preliminary"],
        }
        operational_ranking.append(row)
        if evaluation.estado in OFFICIAL_EVALUATION_STATES:
            official_ranking.append(row)

    operational_ranking.sort(key=lambda row: (row["indice"], row["avance"]), reverse=True)
    official_ranking.sort(key=lambda row: (row["indice"], row["avance"]), reverse=True)

    for position, row in enumerate(operational_ranking, start=1):
        row["operational_rank"] = position
    for position, row in enumerate(official_ranking, start=1):
        row["official_rank"] = position

    show_operational_layer = visible_states != OFFICIAL_EVALUATION_STATES
    default_ranking = operational_ranking if show_operational_layer else official_ranking

    return {
        "ranking": default_ranking,
        "operational_ranking": operational_ranking,
        "official_ranking": official_ranking,
        "total": len(default_ranking),
        "show_operational_layer": show_operational_layer,
        "visible_states": sorted(visible_states),
        "state_counts": state_counts,
    }


def summarize_period_executive(periodo, include_states=None) -> dict:
    visible_states = set(include_states or OFFICIAL_EVALUATION_STATES)
    visible_items = collect_period_evaluation_summaries(periodo, include_states=visible_states)

    dependency_cards = []
    for item in visible_items:
        evaluation = item["evaluacion"]
        summary = item["summary"]
        strongest_axis = max(summary["axes"], key=lambda axis: (axis["promedio"], axis["impacto"], axis["nombre"]))
        weakest_axis = min(summary["axes"], key=lambda axis: (axis["promedio"], -axis["impacto"], axis["nombre"]))
        dependency_cards.append(
            {
                "dependency_id": evaluation.dependencia_id,
                "evaluacion": evaluation,
                "summary": summary,
                "dependencia": evaluation.dependencia.nombre,
                "estado": evaluation.estado,
                "estado_label": summary["state_label"],
                "is_preliminary": summary["is_preliminary"],
                "strongest_axis": strongest_axis,
                "weakest_axis": weakest_axis,
                "critical_axes_count": len(summary["critical_axes"]),
            }
        )

    dependency_cards.sort(
        key=lambda card: (
            card["summary"]["index_score"],
            card["summary"]["completion"],
            card["dependencia"],
        ),
        reverse=True,
    )
    for position, card in enumerate(dependency_cards, start=1):
        card["rank"] = position

    axis_cards = []
    for eje in periodo.cuestionario_version.ejes:
        entries = []
        for item in visible_items:
            evaluation = item["evaluacion"]
            summary = item["summary"]
            axis = summary["axis_map"][eje.id]
            entries.append(
                {
                    "dependency_id": evaluation.dependencia_id,
                    "dependencia": evaluation.dependencia.nombre,
                    "evaluation_id": evaluation.id,
                    "promedio": axis["promedio"],
                    "brecha": axis["brecha"],
                    "priority_label": axis["prioridad"],
                    "priority_slug": axis["priority_slug"],
                    "maturity_label": axis["madurez"],
                    "maturity_slug": axis["maturity_slug"],
                    "estado": evaluation.estado,
                    "estado_label": summary["state_label"],
                    "is_preliminary": summary["is_preliminary"],
                    "completion": summary["completion"],
                }
            )

        if not entries:
            continue

        entries.sort(key=lambda row: (row["promedio"], row["completion"], row["dependencia"]), reverse=True)
        institutional_average = round(sum(row["promedio"] for row in entries) / len(entries), 2)
        gap_average = round(sum(row["brecha"] for row in entries) / len(entries), 2)
        level_label, level_slug = classify_score(institutional_average)
        distribution = maturity_distribution(Counter(row["maturity_slug"] for row in entries), len(entries))
        critical_dependencies = sorted(entries, key=lambda row: (row["promedio"], row["dependencia"]))[:3]
        critical_count = len([row for row in entries if row["priority_slug"] == "critical"])
        axis_cards.append(
            {
                "axis_id": eje.id,
                "clave": eje.clave,
                "nombre": eje.nombre,
                "ponderacion": eje.ponderacion,
                "promedio": institutional_average,
                "brecha_promedio": gap_average,
                "level_label": level_label,
                "level_slug": level_slug,
                "distribution": distribution,
                "dominant_level": dominant_distribution_row(distribution),
                "dependency_count": len(entries),
                "critical_dependency_count": critical_count,
                "critical_dependencies": critical_dependencies,
                "top_dependency": entries[0],
                "bottom_dependency": entries[-1],
                "recommendations": recommendation_for_axis(eje.nombre, institutional_average),
            }
        )

    axis_cards.sort(
        key=lambda card: (
            card["brecha_promedio"],
            card["critical_dependency_count"],
            card["nombre"],
        ),
        reverse=True,
    )

    return {
        "dependency_cards": dependency_cards,
        "axis_cards": axis_cards,
        "visible_states": sorted(visible_states),
        "total_dependencies": len(dependency_cards),
        "total_axes": len(axis_cards),
        "official_count": len([card for card in dependency_cards if not card["is_preliminary"]]),
        "preliminary_count": len([card for card in dependency_cards if card["is_preliminary"]]),
    }


def summarize_axis_for_period(periodo, axis_id: int, include_states=None) -> dict | None:
    axis_version = next((axis for axis in periodo.cuestionario_version.ejes if axis.id == axis_id), None)
    if axis_version is None:
        return None

    visible_states = set(include_states or OFFICIAL_EVALUATION_STATES)
    visible_items = collect_period_evaluation_summaries(periodo, include_states=visible_states)
    ranking = []

    for item in visible_items:
        evaluation = item["evaluacion"]
        summary = item["summary"]
        axis = summary["axis_map"][axis_id]
        ranking.append(
            {
                "dependency_id": evaluation.dependencia_id,
                "dependencia": evaluation.dependencia.nombre,
                "evaluation_id": evaluation.id,
                "promedio": axis["promedio"],
                "brecha": axis["brecha"],
                "priority_label": axis["prioridad"],
                "priority_slug": axis["priority_slug"],
                "maturity_label": axis["madurez"],
                "maturity_slug": axis["maturity_slug"],
                "state": evaluation.estado,
                "state_label": summary["state_label"],
                "is_preliminary": summary["is_preliminary"],
                "completion": summary["completion"],
                "index_score": summary["index_score"],
                "recommendations": axis["recomendaciones"],
            }
        )

    ranking.sort(key=lambda row: (row["promedio"], row["completion"], row["dependencia"]), reverse=True)
    for position, row in enumerate(ranking, start=1):
        row["rank"] = position

    average = round(sum(row["promedio"] for row in ranking) / len(ranking), 2) if ranking else 0
    gap_average = round(sum(row["brecha"] for row in ranking) / len(ranking), 2) if ranking else 0
    level_label, level_slug = classify_score(average)
    distribution = maturity_distribution(Counter(row["maturity_slug"] for row in ranking), len(ranking))
    focus_dependencies = sorted(ranking, key=lambda row: (row["promedio"], row["dependencia"]))[:4]

    return {
        "axis": axis_version,
        "periodo": periodo,
        "ranking": ranking,
        "average": average,
        "gap_average": gap_average,
        "level_label": level_label,
        "level_slug": level_slug,
        "distribution": distribution,
        "dominant_level": dominant_distribution_row(distribution),
        "critical_dependencies": [row for row in focus_dependencies if row["priority_slug"] == "critical"] or focus_dependencies,
        "recommendations": recommendation_for_axis(axis_version.nombre, average),
        "dependency_count": len(ranking),
        "visible_states": sorted(visible_states),
        "official_count": len([row for row in ranking if not row["is_preliminary"]]),
        "preliminary_count": len([row for row in ranking if row["is_preliminary"]]),
    }


def historical_series(evaluaciones: list[Evaluacion]) -> list[dict]:
    data = []
    for evaluacion in evaluaciones:
        if evaluacion.estado not in OFFICIAL_EVALUATION_STATES:
            continue
        summary = summarize_evaluation(evaluacion)
        data.append(
            {
                "periodo": evaluacion.periodo.nombre,
                "indice": summary["index_score"],
                "nivel": summary["level_label"],
                "nivel_slug": summary["level_slug"],
                "fecha_cierre": evaluacion.cerrada_at or evaluacion.aprobada_at,
            }
        )
    return sorted(data, key=lambda item: item["periodo"])
