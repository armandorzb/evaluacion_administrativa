from municipal_diagnostico import create_app
from municipal_diagnostico.extensions import socketio

app = create_app()


if __name__ == "__main__":
    socketio.run(app, debug=True)
