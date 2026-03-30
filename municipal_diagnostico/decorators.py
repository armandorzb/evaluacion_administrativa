from functools import wraps

from flask import abort
from flask_login import current_user, login_required

from municipal_diagnostico.services.activity_logger import log_activity


def _abort_module_access(module_slug: str, message: str):
    log_activity(
        "module_access_denied",
        metadata={"modulo": module_slug, "rol": getattr(current_user, "rol", None)},
    )
    abort(403, description=message)


def role_required(*roles):
    def decorator(func):
        @wraps(func)
        @login_required
        def wrapper(*args, **kwargs):
            if not getattr(current_user, "puede_acceder_diagnostico", False):
                _abort_module_access(
                    "diagnostico",
                    "No cuentas con acceso al módulo Diagnóstico Integral Municipal.",
                )
            if current_user.rol not in roles:
                abort(403)
            return func(*args, **kwargs)

        return wrapper

    return decorator


def wellbeing_role_required(*roles):
    def decorator(func):
        @wraps(func)
        @login_required
        def wrapper(*args, **kwargs):
            if not getattr(current_user, "puede_acceder_bienestar", False):
                _abort_module_access(
                    "bienestar",
                    "No cuentas con acceso al módulo Bienestar Policial.",
                )
            if current_user.rol not in roles:
                abort(403)
            return func(*args, **kwargs)

        return wrapper

    return decorator
