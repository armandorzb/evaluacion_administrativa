from functools import wraps

from flask import abort
from flask_login import current_user, login_required


def role_required(*roles):
    def decorator(func):
        @wraps(func)
        @login_required
        def wrapper(*args, **kwargs):
            if current_user.rol not in roles:
                abort(403)
            return func(*args, **kwargs)

        return wrapper

    return decorator
