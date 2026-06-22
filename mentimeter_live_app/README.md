# Mentimeter Live App

Aplicacion Flask independiente para encuestas y participacion en vivo.

## Ejecutar localmente

```bash
cd mentimeter_live_app
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
python app.py
```

Abre:

- Biblioteca del presentador: `http://127.0.0.1:5000/admin`
- Editor de una presentacion: `http://127.0.0.1:5000/admin/<codigo>`
- Audiencia: `http://127.0.0.1:5000/join`
- Demo: codigo `123456`

En produccion el presentador se protege con `MENTI_ADMIN_USERNAME` y `MENTI_ADMIN_PASSWORD`.
Si esas variables no existen, puede usarse el fallback `MENTI_ADMIN_PIN`; si ninguna existe,
el admin queda abierto para desarrollo local.

La base SQLite se crea automaticamente en `instance/mentimeter.sqlite3`.

## Arquitectura

- `app.py`: factory Flask, rutas REST, eventos Socket.IO, agregadores de resultados y demo inicial.
- `models.py`: modelos SQLAlchemy `PresentationFolder`, `Session`, `Question`, `Option`, `Response`, `Participant`.
- `templates/admin_library.html`: biblioteca inicial con carpetas y acciones de presentacion.
- `templates/admin.html`: editor y pantalla de proyeccion del presentador.
- `templates/join.html` y `templates/audience.html`: flujo mobile-first para entrar y responder.
- `static/js/admin.js`: control de sesiones, preguntas, navegacion y resultados con Chart.js.
- `static/js/audience.js`: conexion anonima, reconexion, render de pregunta activa y envio de respuestas.
- `static/css/app.css`: diseno responsivo para proyeccion y celular.

## Tipos incluidos

- `multiple_choice`: conteo por opcion y barras en vivo.
- `word_cloud`: texto libre agregado por frecuencia.
- `scale`: calificacion numerica con promedio.
- `open_text`: respuestas abiertas en tarjetas.
- `ranking`: ordenamiento con puntaje Borda.
- `quiz`: respuesta correcta, puntaje, timer en cliente y leaderboard.
- Timer server-side para quiz: el servidor marca la pregunta como cerrada al expirar.
- Moderacion manual opcional en `word_cloud` y `open_text`.
- Exports por sesion: CSV, Excel y PDF.
- Insights JSON por sesion.
- Temas visuales: `civic`, `ocean`, `contrast`.
- Biblioteca inicial con carpetas, duplicado y eliminacion de presentaciones.
- Plantillas rapidas y duplicado de preguntas en el editor.

## Integracion municipal

El sistema municipal conserva su `/admin`. La integracion segura usa el puente `/menti/`, que redirige a `MENTI_PUBLIC_URL` si esta configurado. Asi esta app puede correr como servicio separado con sus rutas literales `/admin` y `/join`.

Consulta `PRODUCTION.md` para systemd/nginx y variables de entorno.

## Agregar un nuevo tipo

1. Agrega el identificador a `QUESTION_TYPES` en `app.py`.
2. Define sus reglas en `normalize_question_payload`.
3. Valida el envio en `normalize_response_payload`.
4. Agrega su agregador en `aggregate_question`.
5. Renderiza el formulario y resultados en `static/js/admin.js`.
6. Renderiza la respuesta de audiencia en `static/js/audience.js`.
