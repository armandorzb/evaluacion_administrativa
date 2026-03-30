from __future__ import annotations


MODULE_DIAGNOSTICO = "diagnostico"
MODULE_BIENESTAR = "bienestar"

MODULE_LABELS = {
    MODULE_DIAGNOSTICO: "Diagnóstico Integral Municipal",
    MODULE_BIENESTAR: "Bienestar Policial",
}

WELLBEING_ALLOWED_ROLES = {"administrador", "consulta"}

TRUTHY_VALUES = {"1", "true", "t", "si", "sí", "yes", "y", "on", "x"}
FALSY_VALUES = {"0", "false", "f", "no", "n", "off"}


def default_module_flags(role: str | None) -> dict[str, bool]:
    normalized_role = (role or "").strip().lower()
    return {
        "acceso_diagnostico": True,
        "acceso_bienestar": normalized_role == "administrador",
    }


def normalize_module_flags(
    role: str | None,
    acceso_diagnostico: bool | None = None,
    acceso_bienestar: bool | None = None,
) -> dict[str, bool]:
    defaults = default_module_flags(role)
    normalized_role = (role or "").strip().lower()
    diagnostico = defaults["acceso_diagnostico"] if acceso_diagnostico is None else bool(acceso_diagnostico)
    bienestar = defaults["acceso_bienestar"] if acceso_bienestar is None else bool(acceso_bienestar)

    if normalized_role not in WELLBEING_ALLOWED_ROLES:
        bienestar = False

    return {
        "acceso_diagnostico": diagnostico,
        "acceso_bienestar": bienestar,
    }


def modules_for_user(user) -> list[str]:
    available = []
    if getattr(user, "puede_acceder_diagnostico", False):
        available.append(MODULE_DIAGNOSTICO)
    if getattr(user, "puede_acceder_bienestar", False):
        available.append(MODULE_BIENESTAR)
    return available


def module_label(module_slug: str) -> str:
    return MODULE_LABELS.get(module_slug, module_slug.replace("_", " ").capitalize())


def landing_endpoint_for_user(user) -> str | None:
    available = modules_for_user(user)
    if not available:
        return None
    if len(available) > 1:
        return "dashboard.modules"
    if available[0] == MODULE_BIENESTAR:
        return "wellbeing.dashboard"
    return "dashboard.diagnostic_home"


def endpoint_for_module(user, module_slug: str) -> str | None:
    if module_slug == MODULE_DIAGNOSTICO and getattr(user, "puede_acceder_diagnostico", False):
        return "dashboard.diagnostic_home"
    if module_slug == MODULE_BIENESTAR and getattr(user, "puede_acceder_bienestar", False):
        return "wellbeing.dashboard"
    return None


def parse_optional_flag(raw_value) -> bool | None:
    if raw_value is None:
        return None

    normalized = str(raw_value).strip().lower()
    if not normalized:
        return None
    if normalized in TRUTHY_VALUES:
        return True
    if normalized in FALSY_VALUES:
        return False
    raise ValueError("Valor booleano inválido.")
