# Contexto de la Aplicación

## 1. Resumen ejecutivo

Esta aplicación es una plataforma web interna construida en `Flask` para diseñar cuestionarios, asignarlos a usuarios o dependencias, medir avance de respuesta y generar reportes operativos e institucionales.

El producto nació con un flujo más formal de evaluación por períodos, revisión y cierre. Después se simplificó para operar principalmente con:

`Cuestionarios -> Campañas -> Asignaciones -> Respuestas -> Reportes`

El flujo histórico anterior sigue existiendo en el código para consulta y compatibilidad, pero quedó relegado a modo de solo lectura para no contaminar la operación principal.

---

## 2. Objetivo funcional actual

La aplicación hoy está orientada a cuatro capacidades principales:

1. Diseñar y versionar cuestionarios por secciones/ejes.
2. Crear campañas con una versión congelada de cuestionario.
3. Asignar campañas a usuarios y/o dependencias.
4. Dar seguimiento al avance y generar reportería.

Capacidades complementarias:

- Carga masiva de dependencias, unidades administrativas y usuarios.
- Monitoreo de sesiones y actividad interna.
- Reportes ejecutivos e históricos del flujo legado.
- Exportaciones `PDF`, `Excel` y `CSV` para el módulo legado.

---

## 3. Stack tecnológico

- Backend: `Flask`
- ORM: `Flask-SQLAlchemy` / `SQLAlchemy`
- Migraciones: `Flask-Migrate` / `Alembic`
- Sesiones/autenticación: `Flask-Login`
- Exportación Excel: `openpyxl`
- Exportación PDF: `reportlab`
- Base de datos:
  - Desarrollo local: `SQLite`
  - Producción preparada para: `PostgreSQL` vía `psycopg`
- Frontend:
  - SSR con `Jinja2`
  - CSS propio
  - JavaScript ligero propio

Archivo de entrada:

- [app.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/app.py)

Configuración base:

- [config.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/config.py)

Factory principal:

- [municipal_diagnostico/__init__.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/__init__.py)

---

## 4. Arquitectura general

La aplicación sigue una estructura modular con `app factory`, blueprints y servicios.

### 4.1 Blueprints principales

- [municipal_diagnostico/blueprints/auth.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/blueprints/auth.py)
  - Login, bootstrap inicial y logout.
- [municipal_diagnostico/blueprints/dashboard.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/blueprints/dashboard.py)
  - Tableros por rol y heartbeat de sesión.
- [municipal_diagnostico/blueprints/admin.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/blueprints/admin.py)
  - Catálogos, cuestionarios, monitoreo y vistas administrativas.
- [municipal_diagnostico/blueprints/campaigns.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/blueprints/campaigns.py)
  - Flujo principal simplificado de campañas y asignaciones.
- [municipal_diagnostico/blueprints/reports.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/blueprints/reports.py)
  - Centro ejecutivo y reportes del flujo legado.
- [municipal_diagnostico/blueprints/evaluation.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/blueprints/evaluation.py)
  - Flujo histórico por evaluaciones/períodos.

### 4.2 Servicios

- [municipal_diagnostico/services/campaign_analytics.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/services/campaign_analytics.py)
  - Analítica del flujo simplificado.
- [municipal_diagnostico/services/analytics.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/services/analytics.py)
  - Analítica del flujo legado.
- [municipal_diagnostico/services/activity_logger.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/services/activity_logger.py)
  - Bitácora de sesiones y actividades.
- [municipal_diagnostico/services/importers.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/services/importers.py)
  - Importación masiva desde Excel/CSV.
- [municipal_diagnostico/services/exports.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/services/exports.py)
  - Generación de exportables.
- [municipal_diagnostico/services/notifications.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/services/notifications.py)
  - Notificaciones internas.

### 4.3 Frontend

Base visual:

- [municipal_diagnostico/templates/base.html](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/templates/base.html)
- [municipal_diagnostico/static/style.css](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/static/style.css)
- [municipal_diagnostico/static/app.js](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/static/app.js)

---

## 5. Modelo de dominio

Archivo fuente:

- [municipal_diagnostico/models.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/models.py)

### 5.1 Catálogos y usuarios

- `Dependencia`
- `Area`
- `Usuario`

Roles soportados:

- `administrador`
- `revisor`
- `evaluador`
- `respondente`
- `consulta`

En la UI actual, `evaluador` y `respondente` se tratan funcionalmente como respondentes del cuestionario.

### 5.2 Cuestionarios

- `CuestionarioVersion`
- `EjeVersion`
- `ReactivoVersion`

Características:

- Versionado de cuestionarios.
- Ejes/secciones con ponderación.
- Reactivos con opciones `0` a `3`.
- Posibilidad de clonar y editar borradores.

### 5.3 Flujo simplificado actual

- `CampanaCuestionario`
- `AsignacionCuestionario`
- `RespuestaAsignacion`
- `SoporteSeccion`

Estados de campaña:

- `borrador`
- `activa`
- `cerrada`

Estados de asignación:

- `pendiente`
- `en_progreso`
- `respondido`
- `cerrado`

Tipos de asignación:

- a `usuario`
- a `dependencia`

### 5.4 Flujo legado

- `PeriodoEvaluacion`
- `Evaluacion`
- `EvaluacionAsignacion`
- `Respuesta`
- `EvidenciaEje`
- `ComentarioEje`
- `ObservacionRevision`

Este flujo se conserva por compatibilidad, reportería y consulta histórica.

### 5.5 Monitoreo interno

- `Notificacion`
- `SesionPlataforma`
- `ActividadPlataforma`

---

## 6. Flujo operativo principal

### 6.1 Diseñar cuestionarios

El administrador trabaja en:

- `Admin -> Cuestionarios`

Funciones:

- Crear cuestionarios borrador.
- Clonar versiones.
- Editar ejes y reactivos.
- Publicar versiones.
- Abrir vista metodológica de llenado.

Vista clave:

- [municipal_diagnostico/templates/admin/questionnaires.html](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/templates/admin/questionnaires.html)

### 6.2 Crear campañas

El administrador define:

- nombre
- fechas
- estado
- cuestionario versionado

Ruta principal:

- `/campanas/`

Vista clave:

- [municipal_diagnostico/templates/campaigns/index.html](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/templates/campaigns/index.html)

### 6.3 Crear asignaciones

Una campaña puede asignarse a:

- usuarios
- dependencias
- mezcla de ambos

Para dependencias, puede definirse un `respondente` visible.

Ruta principal:

- `/campanas/asignaciones`

Vista clave:

- [municipal_diagnostico/templates/campaigns/assignments.html](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/templates/campaigns/assignments.html)

### 6.4 Responder cuestionario

Los respondentes trabajan en:

- `/campanas/asignaciones/<id>`

Características actuales:

- autosave
- avance por eje
- soporte opcional por sección
- comentario por reactivo
- envío final al completar 100%

Vista clave:

- [municipal_diagnostico/templates/campaigns/respond.html](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/templates/campaigns/respond.html)

### 6.5 Reportería operativa

Rutas principales:

- `/campanas/reportes`
- `/campanas/reportes/asignaciones/<id>`

Permite ver:

- avance por campaña
- avance por asignación
- resultado por eje
- soportes por sección

Vistas clave:

- [municipal_diagnostico/templates/campaigns/reports.html](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/templates/campaigns/reports.html)
- [municipal_diagnostico/templates/campaigns/assignment_report.html](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/templates/campaigns/assignment_report.html)

---

## 7. Flujo legado e histórico

Aunque el sistema ya se simplificó, permanecen estos componentes:

- `Periodos`
- `Evaluaciones`
- `Revisión`
- `Centro Ejecutivo`
- Reportes por evaluación y por período

Estado actual del legado:

- visible para administración y consulta histórica
- varias pantallas de mutación quedaron desactivadas o en solo lectura
- sigue alimentando el centro ejecutivo y exportables tradicionales

Rutas relevantes:

- `/admin/periodos`
- `/admin/evaluaciones/<id>`
- `/reportes/`
- `/reportes/ejecutivo`
- `/reportes/periodos/<id>`
- `/reportes/evaluaciones/<id>`

---

## 8. Roles y permisos

### Administrador

Puede:

- configurar catálogos
- crear usuarios
- diseñar cuestionarios
- crear campañas
- asignar cuestionarios
- monitorear actividad
- ver reportes completos
- acceder a vistas históricas

### Respondente

Puede:

- ver sus asignaciones
- responder cuestionarios
- guardar avance
- adjuntar soporte por sección
- enviar cuestionarios completos

### Consulta

Puede:

- ver reportes y tableros
- consultar resultados finales
- no puede editar

### Revisor

Permanece por compatibilidad del flujo legado.

---

## 9. Rutas clave del sistema

### Autenticación

- `/auth/login`
- `/auth/bootstrap`
- `/auth/logout`

### Dashboard

- `/dashboard/`
- `/dashboard/heartbeat`

### Administración

- `/admin/catalogos`
- `/admin/cuestionarios`
- `/admin/cuestionarios/<id>/editar`
- `/admin/cuestionarios/<id>/vista-llenado`
- `/admin/monitoreo`

### Campañas

- `/campanas/`
- `/campanas/asignaciones`
- `/campanas/asignaciones/<id>`
- `/campanas/asignaciones/<id>/autosave`
- `/campanas/asignaciones/<id>/enviar`
- `/campanas/soportes/<id>/descargar`
- `/campanas/reportes`
- `/campanas/reportes/asignaciones/<id>`

### Reportes ejecutivos e históricos

- `/reportes/ejecutivo`
- `/reportes/ejecutivo/dependencias/<id>`
- `/reportes/ejecutivo/ejes/<id>`
- `/reportes/`
- `/reportes/evaluaciones/<id>`
- `/reportes/evaluaciones/<id>/pdf`
- `/reportes/periodos/<id>`
- `/reportes/periodos/<id>/excel`
- `/reportes/periodos/<id>/csv`

---

## 10. Configuración por variables de entorno

Definidas en [config.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/config.py):

- `SECRET_KEY`
- `DATABASE_URL`
- `UPLOAD_FOLDER`
- `BOOTSTRAP_ADMIN_EMAIL`
- `BOOTSTRAP_ADMIN_PASSWORD`
- `BOOTSTRAP_ADMIN_NAME`
- `AUTO_INIT_DATABASE`
- `APP_TIMEZONE`

Valores importantes:

- timezone por defecto: `America/Hermosillo`
- base local por defecto: `sqlite:///diagnostico.db`
- auto inicialización: activa por defecto

---

## 11. Seeds e inicialización

Archivo:

- [municipal_diagnostico/seeds.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/seeds.py)

Incluye:

- creación del cuestionario oficial inicial
- bootstrap opcional de administrador
- seed de catálogos base
- comandos CLI

Comandos útiles:

- `flask init-db`
- `flask init-db --with-sample-data`
- `flask create-admin`

---

## 12. Monitoreo y auditoría

Vista principal:

- [municipal_diagnostico/templates/admin/monitoring.html](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/templates/admin/monitoring.html)

Qué registra:

- inicio de sesión
- cierre de sesión
- navegación clave
- autoguardado
- guardado de sección
- envíos
- descargas
- exportaciones
- acciones administrativas

La hora se presenta en `America/Hermosillo`.

---

## 13. Frontend y experiencia visual

Características destacadas:

- UI SSR institucional
- tipografía y layout personalizados
- login centrado con franja superior institucional
- tarjetas y barras de avance en cuestionarios
- menú responsivo con animación
- autosave con feedback visual
- vista metodológica de llenado para evaluar calidad de UI

Archivos base:

- [municipal_diagnostico/static/style.css](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/static/style.css)
- [municipal_diagnostico/static/app.js](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/static/app.js)

---

## 14. Base de datos y migraciones

Migraciones actuales:

- [migrations/versions/828dfa848ed7_initial_schema.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/migrations/versions/828dfa848ed7_initial_schema.py)
- [migrations/versions/d4b2e7c1a901_add_monitoring_and_axis_comments.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/migrations/versions/d4b2e7c1a901_add_monitoring_and_axis_comments.py)
- [migrations/versions/f2a1c9b8d0e4_add_active_flag_to_area.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/migrations/versions/f2a1c9b8d0e4_add_active_flag_to_area.py)
- [migrations/versions/7c3d4ef2a1b0_add_campaigns_and_assignments.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/migrations/versions/7c3d4ef2a1b0_add_campaigns_and_assignments.py)

---

## 15. Pruebas

Tests disponibles:

- [tests/test_bootstrap_flow.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/tests/test_bootstrap_flow.py)
- [tests/test_campaigns_flow.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/tests/test_campaigns_flow.py)
- [tests/test_reports_flow.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/tests/test_reports_flow.py)
- [tests/test_analytics.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/tests/test_analytics.py)

Comando:

- `python -m pytest -q`

---

## 16. Despliegue actual en VPS

Estado operativo actual del despliegue:

- servidor: VPS Ubuntu con `nginx + gunicorn`
- proyecto desplegado en:
  - `/opt/diagnosticoshmo-sistema-para-evaluacion-administrativa`
- datos persistentes en:
  - `/var/lib/diagnosticoshmo-sistema-para-evaluacion-administrativa`
- servicio:
  - `diagnosticoshmo-sistema-para-evaluacion-administrativa`
- puerto interno:
  - `127.0.0.1:8200`
- dominio activo:
  - `https://diagnosticoshmo.187.124.148.20.sslip.io/auth/login`

Además:

- el dominio largo anterior redirige al corto
- se verificó que los otros proyectos del VPS continuaron activos

---

## 17. Estado funcional actual

### Lo principal ya operativo

- autenticación
- bootstrap de admin
- catálogos
- cuestionarios versionados
- campañas
- asignaciones mixtas
- captura con autosave
- soportes por sección
- reportes operativos
- monitoreo
- despliegue en VPS

### Lo que sigue coexistiendo como legado

- períodos
- evaluaciones
- revisión formal
- reportes históricos tradicionales
- centro ejecutivo basado en flujo legado

---

## 18. Deuda técnica y observaciones

Puntos a considerar:

- Persisten algunas cadenas con problemas de codificación en ciertos archivos Python del flujo legado.
- `gunicorn` no está en `requirements.txt`; hoy se instala explícitamente en despliegue.
- El modelo contiene dos dominios conviviendo: el simplificado y el legado. Eso da flexibilidad, pero también eleva complejidad.
- El flujo legado sigue presente por compatibilidad y reportería, aunque la operación principal ya cambió.
- Conviene documentar también un procedimiento formal de backup y restore para producción.

---

## 19. Recomendación de mantenimiento

Si el sistema va a seguir evolucionando sobre el flujo simplificado, lo recomendable es:

1. Mantener `Cuestionarios`, `Campañas`, `Asignaciones`, `Reportes` y `Catálogos` como núcleo.
2. Seguir dejando `Períodos` y `Revisión` únicamente para lectura histórica.
3. Corregir de forma transversal la codificación de textos restantes en Python y templates legacy.
4. Formalizar `README`, `.env.example` y guías de despliegue/operación.

---

## 20. Archivos más importantes para ubicarse rápido

- [app.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/app.py)
- [config.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/config.py)
- [municipal_diagnostico/__init__.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/__init__.py)
- [municipal_diagnostico/models.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/models.py)
- [municipal_diagnostico/blueprints/campaigns.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/blueprints/campaigns.py)
- [municipal_diagnostico/blueprints/admin.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/blueprints/admin.py)
- [municipal_diagnostico/blueprints/reports.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/blueprints/reports.py)
- [municipal_diagnostico/services/campaign_analytics.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/services/campaign_analytics.py)
- [municipal_diagnostico/services/analytics.py](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/services/analytics.py)
- [municipal_diagnostico/templates/base.html](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/templates/base.html)
- [municipal_diagnostico/static/style.css](C:/Users/jarma/Documents/Sistema%20para%20evaluacion%20administrativa/municipal_diagnostico/static/style.css)

