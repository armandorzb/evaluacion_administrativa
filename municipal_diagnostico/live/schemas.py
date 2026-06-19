from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


ACTIVITY_BRAINSTORM = "brainstorm"
ACTIVITY_MULTIPLE_CHOICE = "multiple_choice"
ACTIVITY_SCALE = "scale"
ACTIVITY_RANKING = "ranking"
ACTIVITY_POINTS_100 = "points_100"
ACTIVITY_MATRIX_2X2 = "matrix_2x2"
ACTIVITY_QA = "qa"
ACTIVITY_QUIZ_CHOICE = "quiz_choice"
ACTIVITY_QUIZ_TEXT = "quiz_text"

ACTIVITY_TYPES = {
    ACTIVITY_BRAINSTORM,
    ACTIVITY_MULTIPLE_CHOICE,
    ACTIVITY_SCALE,
    ACTIVITY_RANKING,
    ACTIVITY_POINTS_100,
    ACTIVITY_MATRIX_2X2,
    ACTIVITY_QA,
    ACTIVITY_QUIZ_CHOICE,
    ACTIVITY_QUIZ_TEXT,
}
SESSION_MODES = {"guided", "self_paced"}
ActivityTypeLiteral = Literal[
    "brainstorm",
    "multiple_choice",
    "scale",
    "ranking",
    "points_100",
    "matrix_2x2",
    "qa",
    "quiz_choice",
    "quiz_text",
]


class TemplatePayload(BaseModel):
    tipo: ActivityTypeLiteral
    titulo: str = Field(min_length=3, max_length=180)
    prompt: str = Field(min_length=3, max_length=1200)
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("titulo", "prompt")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def normalize_config(self):
        self.config = normalize_activity_config(self.tipo, self.config)
        return self


class SessionPayload(BaseModel):
    titulo: str = Field(min_length=3, max_length=180)
    descripcion: str | None = Field(default=None, max_length=1200)
    mode: Literal["guided", "self_paced"] = "guided"
    template_ids: list[int] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("titulo")
    @classmethod
    def strip_title(cls, value: str) -> str:
        return value.strip()

    @field_validator("descripcion")
    @classmethod
    def strip_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ActivityPayload(BaseModel):
    template_id: int | None = None
    tipo: ActivityTypeLiteral | None = None
    titulo: str | None = Field(default=None, min_length=3, max_length=180)
    prompt: str | None = Field(default=None, min_length=3, max_length=1200)
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("titulo", "prompt")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value else value

    @model_validator(mode="after")
    def require_template_or_full_payload(self):
        if self.template_id:
            return self
        if not self.tipo or not self.titulo or not self.prompt:
            raise ValueError("Captura template_id o tipo, titulo y prompt.")
        self.config = normalize_activity_config(self.tipo, self.config)
        return self


class PresenterControlPayload(BaseModel):
    session_id: int
    action: Literal[
        "open_session",
        "close_session",
        "open_activity",
        "close_activity",
        "set_mode",
        "reveal_results",
        "hide_results",
        "show_question",
        "set_timer",
    ]
    activity_id: int | None = None
    response_id: int | None = None
    mode: Literal["guided", "self_paced"] | None = None
    timer_seconds: int | None = Field(default=None, ge=0, le=3600)


class SubmitResponsePayload(BaseModel):
    activity_id: int
    participant_token: str | None = Field(default=None, max_length=120)
    payload: dict[str, Any] = Field(default_factory=dict)


def normalize_activity_config(activity_type: str, raw_config: dict[str, Any] | None) -> dict[str, Any]:
    config = dict(raw_config or {})
    common = {
        "show_results": as_bool(config.get("show_results"), default=True),
        "result_layout": normalize_choice(config.get("result_layout"), {"chart", "list", "grid"}, default="chart"),
    }

    if activity_type == ACTIVITY_BRAINSTORM:
        return {
            **common,
            "max_ideas_per_participant": clamp_int(config.get("max_ideas_per_participant"), 1, 20, default=5),
            "max_length": clamp_int(config.get("max_length"), 20, 500, default=160),
            "moderation": normalize_choice(config.get("moderation"), {"none", "manual"}, default="none"),
        }

    if activity_type == ACTIVITY_MULTIPLE_CHOICE:
        options = normalize_text_list(config.get("options"), minimum=2, maximum=10, item_max_length=120, label="Opcion multiple")
        return {**common, "options": options, "chart": str(config.get("chart") or "bar")}

    if activity_type == ACTIVITY_SCALE:
        minimum = clamp_float(config.get("min"), -100, 100, default=1)
        maximum = clamp_float(config.get("max"), -100, 100, default=5)
        if maximum <= minimum:
            raise ValueError("La escala requiere un maximo mayor al minimo.")
        return {
            **common,
            "items": normalize_text_list(config.get("items"), minimum=1, maximum=12, item_max_length=160, label="Escala"),
            "min": minimum,
            "max": maximum,
            "min_label": normalize_optional_text(config.get("min_label"), 80),
            "max_label": normalize_optional_text(config.get("max_label"), 80),
            "allow_skip": as_bool(config.get("allow_skip"), default=False),
        }

    if activity_type == ACTIVITY_RANKING:
        items = normalize_text_list(config.get("items"), minimum=2, maximum=12, item_max_length=160, label="Ranking")
        return {
            **common,
            "items": items,
            "max_ranked": clamp_int(config.get("max_ranked"), 1, len(items), default=len(items)),
            "scoring": "borda",
        }

    if activity_type == ACTIVITY_POINTS_100:
        total_points = clamp_int(config.get("total_points"), 10, 1000, default=100)
        step = clamp_int(config.get("step"), 1, total_points, default=10)
        if total_points % step != 0:
            raise ValueError("El total de puntos debe ser multiplo del paso configurado.")
        return {
            **common,
            "items": normalize_text_list(config.get("items"), minimum=2, maximum=12, item_max_length=160, label="100 puntos"),
            "total_points": total_points,
            "step": step,
        }

    if activity_type == ACTIVITY_MATRIX_2X2:
        minimum = clamp_float(config.get("min"), -100, 100, default=-5)
        maximum = clamp_float(config.get("max"), -100, 100, default=5)
        if maximum <= minimum:
            raise ValueError("La matriz requiere un maximo mayor al minimo.")
        return {
            **common,
            "items": normalize_text_list(config.get("items"), minimum=1, maximum=12, item_max_length=160, label="Matriz 2x2"),
            "x_axis": normalize_axis(config.get("x_axis"), default_min="Bajo", default_max="Alto"),
            "y_axis": normalize_axis(config.get("y_axis"), default_min="Bajo", default_max="Alto"),
            "min": minimum,
            "max": maximum,
            "quadrants": normalize_quadrants(config.get("quadrants")),
        }

    if activity_type == ACTIVITY_QA:
        return {
            **common,
            "moderation": normalize_choice(config.get("moderation"), {"manual", "none"}, default="manual"),
            "allow_upvotes": as_bool(config.get("allow_upvotes"), default=True),
            "visibility": normalize_choice(config.get("visibility"), {"approved", "all"}, default="approved"),
            "global_scope": as_bool(config.get("global_scope"), default=False),
            "max_length": clamp_int(config.get("max_length"), 20, 600, default=280),
        }

    if activity_type == ACTIVITY_QUIZ_CHOICE:
        options = normalize_text_list(config.get("options"), minimum=2, maximum=10, item_max_length=120, label="Quiz")
        correct_options = normalize_text_list(
            config.get("correct_options"),
            minimum=1,
            maximum=len(options),
            item_max_length=120,
            label="Respuestas correctas",
        )
        invalid = [option for option in correct_options if option not in options]
        if invalid:
            raise ValueError("Las respuestas correctas deben existir en las opciones.")
        return {
            **common,
            "options": options,
            "correct_options": correct_options,
            "timer_seconds": clamp_int(config.get("timer_seconds"), 5, 600, default=30),
            "points": clamp_int(config.get("points"), 1, 1000, default=100),
            "show_correct": as_bool(config.get("show_correct"), default=True),
        }

    if activity_type == ACTIVITY_QUIZ_TEXT:
        answers = normalize_text_list(config.get("answers"), minimum=1, maximum=20, item_max_length=120, label="Respuestas correctas")
        return {
            **common,
            "answers": answers,
            "timer_seconds": clamp_int(config.get("timer_seconds"), 5, 600, default=30),
            "points": clamp_int(config.get("points"), 1, 1000, default=100),
            "case_sensitive": as_bool(config.get("case_sensitive"), default=False),
            "show_correct": as_bool(config.get("show_correct"), default=True),
        }

    raise ValueError("Tipo de actividad no soportado.")


def normalize_response_payload(activity_type: str, config: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    if activity_type == ACTIVITY_BRAINSTORM:
        idea = str(payload.get("idea") or payload.get("text") or "").strip()
        max_length = int(config.get("max_length") or 160)
        if len(idea) < 2:
            raise ValueError("Captura una idea antes de enviar.")
        if len(idea) > max_length:
            raise ValueError(f"La idea no puede superar {max_length} caracteres.")
        return {"idea": idea}

    if activity_type == ACTIVITY_MULTIPLE_CHOICE:
        choice = str(payload.get("choice") or "").strip()
        options = [str(option) for option in config.get("options", [])]
        if choice not in options:
            raise ValueError("Selecciona una opcion valida.")
        return {"choice": choice}

    if activity_type == ACTIVITY_SCALE:
        return {"ratings": normalize_scale_response(config, payload)}

    if activity_type == ACTIVITY_RANKING:
        return {"ranking": normalize_ranking_response(config, payload)}

    if activity_type == ACTIVITY_POINTS_100:
        return {"points": normalize_points_response(config, payload)}

    if activity_type == ACTIVITY_MATRIX_2X2:
        return {"ratings": normalize_matrix_response(config, payload)}

    if activity_type == ACTIVITY_QA:
        question = str(payload.get("question") or payload.get("text") or "").strip()
        max_length = int(config.get("max_length") or 280)
        if len(question) < 3:
            raise ValueError("Captura una pregunta antes de enviar.")
        if len(question) > max_length:
            raise ValueError(f"La pregunta no puede superar {max_length} caracteres.")
        return {"question": question}

    if activity_type == ACTIVITY_QUIZ_CHOICE:
        choice = str(payload.get("choice") or "").strip()
        options = [str(option) for option in config.get("options", [])]
        if choice not in options:
            raise ValueError("Selecciona una opcion valida.")
        is_correct = choice in [str(option) for option in config.get("correct_options", [])]
        return {
            "choice": choice,
            "is_correct": is_correct,
            "score_awarded": int(config.get("points") or 100) if is_correct else 0,
        }

    if activity_type == ACTIVITY_QUIZ_TEXT:
        answer = str(payload.get("answer") or "").strip()
        if not answer:
            raise ValueError("Captura una respuesta antes de enviar.")
        if len(answer) > 240:
            raise ValueError("La respuesta no puede superar 240 caracteres.")
        case_sensitive = bool(config.get("case_sensitive"))
        expected = [str(item).strip() for item in config.get("answers", [])]
        compare_answer = answer if case_sensitive else answer.casefold()
        compare_expected = expected if case_sensitive else [item.casefold() for item in expected]
        is_correct = compare_answer in compare_expected
        return {
            "answer": answer,
            "is_correct": is_correct,
            "score_awarded": int(config.get("points") or 100) if is_correct else 0,
        }

    raise ValueError("Tipo de actividad no soportado.")


def normalize_scale_response(config: dict[str, Any], payload: dict[str, Any]) -> dict[str, float]:
    items = [str(item) for item in config.get("items", [])]
    minimum = float(config.get("min", 1))
    maximum = float(config.get("max", 5))
    raw_ratings = payload.get("ratings") or payload
    if not isinstance(raw_ratings, dict):
        raise ValueError("La escala requiere calificaciones por item.")
    ratings: dict[str, float] = {}
    for item in items:
        raw_value = raw_ratings.get(item)
        if raw_value in (None, ""):
            if config.get("allow_skip"):
                continue
            raise ValueError("Responde todos los items de la escala.")
        value = clamp_float(raw_value, minimum, maximum, default=minimum)
        ratings[item] = value
    if not ratings:
        raise ValueError("Captura al menos una calificacion.")
    return ratings


def normalize_ranking_response(config: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    raw_ranking = payload.get("ranking") or []
    if isinstance(raw_ranking, str):
        raw_ranking = [item.strip() for item in raw_ranking.replace(",", "\n").splitlines()]
    if not isinstance(raw_ranking, list):
        raise ValueError("El ranking requiere una lista ordenada.")
    items = [str(item) for item in config.get("items", [])]
    max_ranked = int(config.get("max_ranked") or len(items))
    ranking: list[str] = []
    for item in raw_ranking:
        value = str(item).strip()
        if value and value not in ranking:
            ranking.append(value)
    if not ranking:
        raise ValueError("Selecciona al menos un elemento del ranking.")
    if len(ranking) > max_ranked:
        raise ValueError(f"Puedes rankear hasta {max_ranked} elementos.")
    if any(item not in items for item in ranking):
        raise ValueError("El ranking contiene un elemento invalido.")
    return ranking


def normalize_points_response(config: dict[str, Any], payload: dict[str, Any]) -> dict[str, int]:
    raw_points = payload.get("points") or {}
    if not isinstance(raw_points, dict):
        raise ValueError("La dinamica 100 puntos requiere puntos por item.")
    items = [str(item) for item in config.get("items", [])]
    total_points = int(config.get("total_points") or 100)
    step = int(config.get("step") or 10)
    points: dict[str, int] = {}
    for item in items:
        try:
            value = int(raw_points.get(item) or 0)
        except (TypeError, ValueError):
            raise ValueError("Los puntos deben ser numeros enteros.") from None
        if value < 0:
            raise ValueError("Los puntos no pueden ser negativos.")
        if value % step != 0:
            raise ValueError(f"Los puntos deben asignarse en pasos de {step}.")
        points[item] = value
    if sum(points.values()) != total_points:
        raise ValueError(f"Debes distribuir exactamente {total_points} puntos.")
    return points


def normalize_matrix_response(config: dict[str, Any], payload: dict[str, Any]) -> dict[str, dict[str, float]]:
    raw_ratings = payload.get("ratings") or payload
    if not isinstance(raw_ratings, dict):
        raise ValueError("La matriz requiere coordenadas por item.")
    items = [str(item) for item in config.get("items", [])]
    minimum = float(config.get("min", -5))
    maximum = float(config.get("max", 5))
    ratings: dict[str, dict[str, float]] = {}
    for item in items:
        raw_value = raw_ratings.get(item)
        if raw_value in (None, ""):
            continue
        if isinstance(raw_value, dict):
            raw_x = raw_value.get("x")
            raw_y = raw_value.get("y")
        elif isinstance(raw_value, (list, tuple)) and len(raw_value) >= 2:
            raw_x, raw_y = raw_value[0], raw_value[1]
        else:
            raise ValueError("Cada item de matriz requiere coordenadas x/y.")
        ratings[item] = {
            "x": clamp_float(raw_x, minimum, maximum, default=0),
            "y": clamp_float(raw_y, minimum, maximum, default=0),
        }
    if not ratings:
        raise ValueError("Ubica al menos un item en la matriz.")
    return ratings


def normalize_text_list(
    value: Any,
    *,
    minimum: int,
    maximum: int,
    item_max_length: int,
    label: str,
) -> list[str]:
    if isinstance(value, str):
        raw_values = value.replace(",", "\n").splitlines()
    elif isinstance(value, (list, tuple)):
        raw_values = value
    else:
        raw_values = []
    items: list[str] = []
    for raw_item in raw_values:
        item = str(raw_item).strip()
        if item and item not in items:
            items.append(item[:item_max_length])
    if len(items) < minimum:
        raise ValueError(f"{label} requiere al menos {minimum} elemento(s).")
    if len(items) > maximum:
        raise ValueError(f"{label} permite hasta {maximum} elementos.")
    return items


def normalize_axis(value: Any, *, default_min: str, default_max: str) -> dict[str, str]:
    if not isinstance(value, dict):
        value = {}
    return {
        "min_label": normalize_optional_text(value.get("min_label"), 80) or default_min,
        "max_label": normalize_optional_text(value.get("max_label"), 80) or default_max,
    }


def normalize_quadrants(value: Any) -> list[str]:
    if not value:
        return []
    return normalize_text_list(value, minimum=0, maximum=4, item_max_length=80, label="Cuadrantes")


def normalize_optional_text(value: Any, max_length: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:max_length] if text else None


def normalize_choice(value: Any, choices: set[str], *, default: str) -> str:
    candidate = str(value or default).strip()
    return candidate if candidate in choices else default


def as_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on", "si", "y"}


def clamp_int(value: Any, minimum: int, maximum: int, *, default: int) -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        numeric = default
    return max(minimum, min(maximum, numeric))


def clamp_float(value: Any, minimum: float, maximum: float, *, default: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = default
    return max(minimum, min(maximum, numeric))
