from __future__ import annotations


def init_live_module(app, socketio, db) -> None:
    from municipal_diagnostico.live.blueprint import bp
    from municipal_diagnostico.live.events import register_socketio_events

    app.register_blueprint(bp)
    register_socketio_events(socketio)
