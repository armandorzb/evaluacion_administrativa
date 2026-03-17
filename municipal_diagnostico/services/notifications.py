from municipal_diagnostico.extensions import db
from municipal_diagnostico.models import Notificacion, Usuario


def notify_user(usuario: Usuario, tipo: str, mensaje: str, enlace: str | None = None) -> None:
    db.session.add(
        Notificacion(
            usuario=usuario,
            tipo=tipo,
            mensaje=mensaje,
            enlace=enlace,
        )
    )


def notify_many(usuarios: list[Usuario], tipo: str, mensaje: str, enlace: str | None = None) -> None:
    sent_to: set[int] = set()
    for usuario in usuarios:
        if usuario.id in sent_to:
            continue
        sent_to.add(usuario.id)
        notify_user(usuario, tipo, mensaje, enlace)
