from __future__ import annotations

from flask_login import UserMixin
from sqlalchemy import UniqueConstraint, event
from sqlalchemy.dialects.postgresql import JSONB
from werkzeug.security import check_password_hash, generate_password_hash

from municipal_diagnostico.extensions import db
from municipal_diagnostico.services.module_access import (
    ISO9001_ALLOWED_ROLES,
    LIVE_ALLOWED_ROLES,
    MODULE_BIENESTAR,
    MODULE_DIAGNOSTICO,
    MODULE_ISO9001,
    MODULE_LIVE,
    WELLBEING_ALLOWED_ROLES,
    normalize_module_flags,
)
from municipal_diagnostico.timeutils import utcnow


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )


def json_payload_type():
    return db.JSON().with_variant(JSONB, "postgresql")


class Dependencia(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(160), unique=True, nullable=False)
    tipo = db.Column(db.String(120), nullable=False, default="Administrativa")
    descripcion = db.Column(db.Text)
    activa = db.Column(db.Boolean, default=True, nullable=False)

    areas = db.relationship(
        "Area",
        back_populates="dependencia",
        cascade="all, delete-orphan",
        order_by="Area.nombre",
    )
    usuarios = db.relationship("Usuario", back_populates="dependencia")
    evaluaciones = db.relationship("Evaluacion", back_populates="dependencia")
    asignaciones_cuestionario = db.relationship(
        "AsignacionCuestionario",
        back_populates="dependencia",
        foreign_keys="AsignacionCuestionario.dependencia_id",
    )
    iso9001_evaluaciones = db.relationship("Iso9001Evaluacion", back_populates="dependencia")

    @property
    def areas_activas(self):
        return [area for area in self.areas if getattr(area, "activa", True)]

    @property
    def total_areas_activas(self) -> int:
        return len(self.areas_activas)

    @property
    def total_usuarios_activos(self) -> int:
        return sum(1 for usuario in self.usuarios if usuario.activo)


class Area(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(160), nullable=False)
    dependencia_id = db.Column(db.Integer, db.ForeignKey("dependencia.id"), nullable=False)
    activa = db.Column(db.Boolean, default=True, nullable=False)

    dependencia = db.relationship("Dependencia", back_populates="areas")
    usuarios = db.relationship("Usuario", back_populates="area")
    asignaciones = db.relationship("EvaluacionAsignacion", back_populates="area")
    respuestas = db.relationship("Respuesta", back_populates="area")

    __table_args__ = (
        UniqueConstraint("dependencia_id", "nombre", name="uq_area_dependencia_nombre"),
    )


class Usuario(UserMixin, TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(160), nullable=False)
    correo = db.Column(db.String(160), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.String(30), nullable=False)
    activo = db.Column(db.Boolean, default=True, nullable=False)
    acceso_diagnostico = db.Column(db.Boolean, nullable=False, default=True)
    acceso_bienestar = db.Column(db.Boolean, nullable=False, default=False)
    acceso_iso9001 = db.Column(db.Boolean, nullable=False, default=False)
    acceso_live = db.Column(db.Boolean, nullable=False, default=False)
    dependencia_id = db.Column(db.Integer, db.ForeignKey("dependencia.id"))
    area_id = db.Column(db.Integer, db.ForeignKey("area.id"))

    dependencia = db.relationship("Dependencia", back_populates="usuarios")
    area = db.relationship("Area", back_populates="usuarios")
    cuestionarios_creados = db.relationship(
        "CuestionarioVersion",
        back_populates="creado_por",
        foreign_keys="CuestionarioVersion.creado_por_id",
    )
    periodos_creados = db.relationship(
        "PeriodoEvaluacion",
        back_populates="creado_por",
        foreign_keys="PeriodoEvaluacion.creado_por_id",
    )
    evaluaciones_revisadas = db.relationship(
        "Evaluacion",
        back_populates="revisor",
        foreign_keys="Evaluacion.revisor_id",
    )
    respuestas_capturadas = db.relationship(
        "Respuesta",
        back_populates="usuario_captura",
        foreign_keys="Respuesta.usuario_captura_id",
    )
    evidencias_subidas = db.relationship(
        "EvidenciaEje",
        back_populates="usuario",
        foreign_keys="EvidenciaEje.usuario_id",
    )
    observaciones = db.relationship(
        "ObservacionRevision",
        back_populates="autor",
        foreign_keys="ObservacionRevision.autor_id",
    )
    comentarios_eje = db.relationship("ComentarioEje", back_populates="usuario")
    notificaciones = db.relationship("Notificacion", back_populates="usuario")
    asignaciones = db.relationship("EvaluacionAsignacion", back_populates="usuario")
    sesiones = db.relationship("SesionPlataforma", back_populates="usuario")
    actividades = db.relationship("ActividadPlataforma", back_populates="usuario")
    campanas_creadas = db.relationship(
        "CampanaCuestionario",
        back_populates="creado_por",
        foreign_keys="CampanaCuestionario.creado_por_id",
    )
    asignaciones_cuestionario = db.relationship(
        "AsignacionCuestionario",
        back_populates="usuario",
        foreign_keys="AsignacionCuestionario.usuario_id",
    )
    asignaciones_respondente = db.relationship(
        "AsignacionCuestionario",
        back_populates="respondente",
        foreign_keys="AsignacionCuestionario.respondente_id",
    )
    respuestas_asignacion = db.relationship(
        "RespuestaAsignacion",
        back_populates="usuario",
        foreign_keys="RespuestaAsignacion.usuario_id",
    )
    soportes_seccion = db.relationship(
        "SoporteSeccion",
        back_populates="usuario",
        foreign_keys="SoporteSeccion.usuario_id",
    )
    iso9001_ciclos_creados = db.relationship(
        "Iso9001Ciclo",
        back_populates="creado_por",
        foreign_keys="Iso9001Ciclo.creado_por_id",
    )
    iso9001_asignaciones = db.relationship(
        "Iso9001Asignacion",
        back_populates="usuario",
        foreign_keys="Iso9001Asignacion.usuario_id",
    )
    iso9001_revisiones = db.relationship(
        "Iso9001Evaluacion",
        back_populates="revisor",
        foreign_keys="Iso9001Evaluacion.revisor_id",
    )
    iso9001_respuestas = db.relationship(
        "Iso9001Respuesta",
        back_populates="usuario",
        foreign_keys="Iso9001Respuesta.usuario_id",
    )
    iso9001_evidencias = db.relationship(
        "Iso9001Evidencia",
        back_populates="usuario",
        foreign_keys="Iso9001Evidencia.usuario_id",
    )
    iso9001_observaciones = db.relationship(
        "Iso9001ObservacionRevision",
        back_populates="autor",
        foreign_keys="Iso9001ObservacionRevision.autor_id",
    )
    live_templates = db.relationship(
        "LiveReactivoTemplate",
        back_populates="creado_por",
        foreign_keys="LiveReactivoTemplate.creado_por_id",
    )
    live_sessions_presentadas = db.relationship(
        "LiveSession",
        back_populates="presentador",
        foreign_keys="LiveSession.presentador_id",
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        explicit_module_flags = {"acceso_diagnostico", "acceso_bienestar", "acceso_iso9001", "acceso_live"}
        acceso_live = kwargs.get("acceso_live", getattr(self, "acceso_live", None))
        if "acceso_live" not in kwargs and explicit_module_flags.intersection(kwargs):
            acceso_live = False
        normalized = normalize_module_flags(
            kwargs.get("rol", getattr(self, "rol", None)),
            kwargs.get("acceso_diagnostico", getattr(self, "acceso_diagnostico", None)),
            kwargs.get("acceso_bienestar", getattr(self, "acceso_bienestar", None)),
            kwargs.get("acceso_iso9001", getattr(self, "acceso_iso9001", None)),
            acceso_live,
        )
        self.acceso_diagnostico = normalized["acceso_diagnostico"]
        self.acceso_bienestar = normalized["acceso_bienestar"]
        self.acceso_iso9001 = normalized["acceso_iso9001"]
        self.acceso_live = normalized["acceso_live"]

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def sync_module_accesses(self) -> None:
        normalized = normalize_module_flags(
            self.rol,
            self.acceso_diagnostico,
            self.acceso_bienestar,
            self.acceso_iso9001,
            self.acceso_live,
        )
        self.acceso_diagnostico = normalized["acceso_diagnostico"]
        self.acceso_bienestar = normalized["acceso_bienestar"]
        self.acceso_iso9001 = normalized["acceso_iso9001"]
        self.acceso_live = normalized["acceso_live"]

    @property
    def nombre_rol(self) -> str:
        return {
            "administrador": "Administrador",
            "revisor": "Revisor",
            "evaluador": "Respondente",
            "respondente": "Respondente",
            "consulta": "Consulta",
        }.get(self.rol, self.rol)

    @property
    def puede_acceder_diagnostico(self) -> bool:
        return self.activo and bool(self.acceso_diagnostico)

    @property
    def puede_acceder_bienestar(self) -> bool:
        return (
            self.activo
            and bool(self.acceso_bienestar)
            and self.rol in WELLBEING_ALLOWED_ROLES
        )

    @property
    def puede_acceder_iso9001(self) -> bool:
        return (
            self.activo
            and bool(self.acceso_iso9001)
            and self.rol in ISO9001_ALLOWED_ROLES
        )

    @property
    def puede_acceder_live(self) -> bool:
        return (
            self.activo
            and bool(self.acceso_live)
            and self.rol in LIVE_ALLOWED_ROLES
        )

    @property
    def modulos_disponibles(self) -> list[str]:
        modules = []
        if self.puede_acceder_diagnostico:
            modules.append(MODULE_DIAGNOSTICO)
        if self.puede_acceder_bienestar:
            modules.append(MODULE_BIENESTAR)
        if self.puede_acceder_iso9001:
            modules.append(MODULE_ISO9001)
        if self.puede_acceder_live:
            modules.append(MODULE_LIVE)
        return modules

    @property
    def tiene_selector_modulos(self) -> bool:
        return len(self.modulos_disponibles) > 1

    @property
    def modulos_asignados_label(self) -> str:
        labels = []
        if self.acceso_diagnostico:
            labels.append("Diagnóstico")
        if self.acceso_bienestar:
            labels.append("Bienestar")
        if self.acceso_iso9001:
            labels.append("ISO 9001")
        if self.acceso_live:
            labels.append("Live")
        return " · ".join(labels) if labels else "Sin acceso"


@event.listens_for(Usuario, "before_insert")
@event.listens_for(Usuario, "before_update")
def sync_usuario_module_accesses(_mapper, _connection, target: Usuario) -> None:
    target.sync_module_accesses()


class CuestionarioVersion(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(160), nullable=False)
    descripcion = db.Column(db.Text)
    estado = db.Column(db.String(20), default="borrador", nullable=False)
    publicado_at = db.Column(db.DateTime)
    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuario.id"))

    creado_por = db.relationship("Usuario", back_populates="cuestionarios_creados")
    ejes = db.relationship(
        "EjeVersion",
        back_populates="cuestionario_version",
        cascade="all, delete-orphan",
        order_by="EjeVersion.orden",
    )
    periodos = db.relationship("PeriodoEvaluacion", back_populates="cuestionario_version")
    campanas = db.relationship("CampanaCuestionario", back_populates="cuestionario_version")


class EjeVersion(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cuestionario_version_id = db.Column(
        db.Integer,
        db.ForeignKey("cuestionario_version.id"),
        nullable=False,
    )
    clave = db.Column(db.String(10), nullable=False)
    orden = db.Column(db.Integer, nullable=False)
    nombre = db.Column(db.String(160), nullable=False)
    descripcion = db.Column(db.Text)
    ponderacion = db.Column(db.Float, nullable=False)

    cuestionario_version = db.relationship("CuestionarioVersion", back_populates="ejes")
    reactivos = db.relationship(
        "ReactivoVersion",
        back_populates="eje_version",
        cascade="all, delete-orphan",
        order_by="ReactivoVersion.orden",
    )
    evidencias = db.relationship("EvidenciaEje", back_populates="eje_version")
    observaciones = db.relationship("ObservacionRevision", back_populates="eje_version")
    comentarios = db.relationship("ComentarioEje", back_populates="eje_version")
    soportes_seccion = db.relationship("SoporteSeccion", back_populates="eje_version")


class ReactivoVersion(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    eje_version_id = db.Column(db.Integer, db.ForeignKey("eje_version.id"), nullable=False)
    codigo = db.Column(db.String(10), nullable=False)
    orden = db.Column(db.Integer, nullable=False)
    pregunta = db.Column(db.Text, nullable=False)
    opciones = db.Column(db.JSON, nullable=False)

    eje_version = db.relationship("EjeVersion", back_populates="reactivos")
    respuestas = db.relationship("Respuesta", back_populates="reactivo_version")
    respuestas_asignacion = db.relationship(
        "RespuestaAsignacion",
        back_populates="reactivo_version",
    )

    __table_args__ = (
        UniqueConstraint("eje_version_id", "orden", name="uq_reactivo_eje_orden"),
    )


class PeriodoEvaluacion(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(160), nullable=False, unique=True)
    descripcion = db.Column(db.Text)
    estado = db.Column(db.String(20), default="borrador", nullable=False)
    fecha_inicio = db.Column(db.Date, nullable=False)
    fecha_cierre = db.Column(db.Date, nullable=False)
    cuestionario_version_id = db.Column(
        db.Integer,
        db.ForeignKey("cuestionario_version.id"),
        nullable=False,
    )
    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuario.id"))

    cuestionario_version = db.relationship("CuestionarioVersion", back_populates="periodos")
    creado_por = db.relationship("Usuario", back_populates="periodos_creados")
    evaluaciones = db.relationship(
        "Evaluacion",
        back_populates="periodo",
        cascade="all, delete-orphan",
    )

    @property
    def esta_abierto(self) -> bool:
        return self.estado in {"abierto", "reabierto"}


class CampanaCuestionario(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(160), nullable=False, unique=True)
    descripcion = db.Column(db.Text)
    estado = db.Column(db.String(20), default="borrador", nullable=False)
    fecha_apertura = db.Column(db.Date, nullable=False)
    fecha_limite = db.Column(db.Date, nullable=False)
    cuestionario_version_id = db.Column(
        db.Integer,
        db.ForeignKey("cuestionario_version.id"),
        nullable=False,
    )
    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuario.id"))

    cuestionario_version = db.relationship("CuestionarioVersion", back_populates="campanas")
    creado_por = db.relationship("Usuario", back_populates="campanas_creadas")
    asignaciones = db.relationship(
        "AsignacionCuestionario",
        back_populates="campana",
        cascade="all, delete-orphan",
        order_by="AsignacionCuestionario.updated_at.desc()",
    )

    @property
    def esta_activa(self) -> bool:
        return self.estado == "activa"


class AsignacionCuestionario(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    campana_id = db.Column(db.Integer, db.ForeignKey("campana_cuestionario.id"), nullable=False)
    target_type = db.Column(db.String(20), nullable=False, default="usuario")
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"))
    dependencia_id = db.Column(db.Integer, db.ForeignKey("dependencia.id"))
    respondente_id = db.Column(db.Integer, db.ForeignKey("usuario.id"))
    estado = db.Column(db.String(20), default="pendiente", nullable=False)
    progreso = db.Column(db.Float, default=0.0, nullable=False)
    fecha_inicio = db.Column(db.DateTime)
    fecha_envio = db.Column(db.DateTime)
    cerrada_at = db.Column(db.DateTime)
    ultima_actividad_at = db.Column(db.DateTime)

    campana = db.relationship("CampanaCuestionario", back_populates="asignaciones")
    usuario = db.relationship(
        "Usuario",
        back_populates="asignaciones_cuestionario",
        foreign_keys=[usuario_id],
    )
    dependencia = db.relationship(
        "Dependencia",
        back_populates="asignaciones_cuestionario",
        foreign_keys=[dependencia_id],
    )
    respondente = db.relationship(
        "Usuario",
        back_populates="asignaciones_respondente",
        foreign_keys=[respondente_id],
    )
    respuestas = db.relationship(
        "RespuestaAsignacion",
        back_populates="asignacion",
        cascade="all, delete-orphan",
    )
    soportes = db.relationship(
        "SoporteSeccion",
        back_populates="asignacion",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "campana_id",
            "target_type",
            "usuario_id",
            "dependencia_id",
            name="uq_campana_target_asignacion",
        ),
    )

    @property
    def cuestionario_version(self) -> CuestionarioVersion:
        return self.campana.cuestionario_version

    @property
    def objetivo_nombre(self) -> str:
        if self.target_type == "usuario" and self.usuario:
            return self.usuario.nombre
        if self.dependencia:
            return self.dependencia.nombre
        return "Asignación sin objetivo"

    @property
    def dependencia_visible(self) -> Dependencia | None:
        return self.dependencia or (self.usuario.dependencia if self.usuario else None)

    @property
    def puede_responder(self) -> bool:
        return (
            self.estado in {"pendiente", "en_progreso"}
            and self.campana is not None
            and self.campana.esta_activa
            and self.respondente_id is not None
        )


class RespuestaAsignacion(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asignacion_id = db.Column(db.Integer, db.ForeignKey("asignacion_cuestionario.id"), nullable=False)
    reactivo_version_id = db.Column(
        db.Integer,
        db.ForeignKey("reactivo_version.id"),
        nullable=False,
    )
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    valor = db.Column(db.Integer, nullable=False)
    comentario = db.Column(db.Text)

    asignacion = db.relationship("AsignacionCuestionario", back_populates="respuestas")
    reactivo_version = db.relationship("ReactivoVersion", back_populates="respuestas_asignacion")
    usuario = db.relationship("Usuario", back_populates="respuestas_asignacion")

    __table_args__ = (
        UniqueConstraint(
            "asignacion_id",
            "reactivo_version_id",
            name="uq_respuesta_asignacion_reactivo",
        ),
    )


class SoporteSeccion(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asignacion_id = db.Column(db.Integer, db.ForeignKey("asignacion_cuestionario.id"), nullable=False)
    eje_version_id = db.Column(db.Integer, db.ForeignKey("eje_version.id"), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    comentario = db.Column(db.Text)
    archivo_nombre_original = db.Column(db.String(255))
    archivo_guardado = db.Column(db.String(255))
    mime_type = db.Column(db.String(120))
    tamano_bytes = db.Column(db.Integer)

    asignacion = db.relationship("AsignacionCuestionario", back_populates="soportes")
    eje_version = db.relationship("EjeVersion", back_populates="soportes_seccion")
    usuario = db.relationship("Usuario", back_populates="soportes_seccion")

    __table_args__ = (
        UniqueConstraint(
            "asignacion_id",
            "eje_version_id",
            name="uq_soporte_asignacion_eje",
        ),
    )


class BienestarPregunta(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    orden = db.Column(db.Integer, nullable=False, unique=True)
    dimension = db.Column(db.String(100), nullable=False)
    texto = db.Column(db.Text, nullable=False)
    opciones = db.Column(db.JSON, nullable=False)
    tipo_reactivo = db.Column(db.String(20), nullable=False, default="indicador")
    activa = db.Column(db.Boolean, default=True, nullable=False)

    respuestas = db.relationship(
        "BienestarRespuesta",
        back_populates="pregunta",
    )


class BienestarEncuesta(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hash_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    estrato = db.Column(db.String(10), nullable=False, default="E1")
    iibp = db.Column(db.Float)
    ivsp = db.Column(db.Float)
    estado = db.Column(db.String(20), nullable=False, default="abandonada")
    ultima_pregunta = db.Column(db.Integer, default=0, nullable=False)
    completada_at = db.Column(db.DateTime)

    respuestas = db.relationship(
        "BienestarRespuesta",
        back_populates="encuesta",
        cascade="all, delete-orphan",
        order_by="BienestarRespuesta.pregunta_id",
    )


class BienestarRespuesta(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    encuesta_id = db.Column(db.Integer, db.ForeignKey("bienestar_encuesta.id"), nullable=False)
    pregunta_id = db.Column(db.Integer, db.ForeignKey("bienestar_pregunta.id"), nullable=False)
    dimension = db.Column(db.String(100), nullable=False)
    valor = db.Column(db.Integer, nullable=False)

    encuesta = db.relationship("BienestarEncuesta", back_populates="respuestas")
    pregunta = db.relationship("BienestarPregunta", back_populates="respuestas")

    __table_args__ = (
        UniqueConstraint(
            "encuesta_id",
            "pregunta_id",
            name="uq_bienestar_encuesta_pregunta",
        ),
    )


class Iso9001CuestionarioVersion(TimestampMixin, db.Model):
    __tablename__ = "iso9001_cuestionario_version"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)
    nombre = db.Column(db.String(180), nullable=False)
    descripcion = db.Column(db.Text)
    norma = db.Column(db.String(80), nullable=False, default="ISO 9001:2015")
    estado = db.Column(db.String(20), default="publicado", nullable=False)
    publicado_at = db.Column(db.DateTime, default=utcnow)

    clausulas = db.relationship(
        "Iso9001Clausula",
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="Iso9001Clausula.orden",
    )
    ciclos = db.relationship("Iso9001Ciclo", back_populates="version")


class Iso9001Clausula(TimestampMixin, db.Model):
    __tablename__ = "iso9001_clausula"

    id = db.Column(db.Integer, primary_key=True)
    version_id = db.Column(db.Integer, db.ForeignKey("iso9001_cuestionario_version.id"), nullable=False)
    numero = db.Column(db.String(10), nullable=False)
    nombre = db.Column(db.String(180), nullable=False)
    orden = db.Column(db.Integer, nullable=False)

    version = db.relationship("Iso9001CuestionarioVersion", back_populates="clausulas")
    apartados = db.relationship(
        "Iso9001Apartado",
        back_populates="clausula",
        cascade="all, delete-orphan",
        order_by="Iso9001Apartado.orden",
    )

    __table_args__ = (
        UniqueConstraint("version_id", "numero", name="uq_iso9001_clausula_version_numero"),
    )


class Iso9001Apartado(TimestampMixin, db.Model):
    __tablename__ = "iso9001_apartado"

    id = db.Column(db.Integer, primary_key=True)
    clausula_id = db.Column(db.Integer, db.ForeignKey("iso9001_clausula.id"), nullable=False)
    codigo = db.Column(db.String(20), nullable=False)
    nombre = db.Column(db.String(220), nullable=False)
    orden = db.Column(db.Integer, nullable=False)

    clausula = db.relationship("Iso9001Clausula", back_populates="apartados")
    reactivos = db.relationship(
        "Iso9001Reactivo",
        back_populates="apartado",
        cascade="all, delete-orphan",
        order_by="Iso9001Reactivo.orden",
    )

    __table_args__ = (
        UniqueConstraint("clausula_id", "codigo", name="uq_iso9001_apartado_clausula_codigo"),
    )


class Iso9001Reactivo(TimestampMixin, db.Model):
    __tablename__ = "iso9001_reactivo"

    id = db.Column(db.Integer, primary_key=True)
    apartado_id = db.Column(db.Integer, db.ForeignKey("iso9001_apartado.id"), nullable=False)
    numero = db.Column(db.Integer, nullable=False)
    orden = db.Column(db.Integer, nullable=False)
    texto = db.Column(db.Text, nullable=False)
    evidencia_sugerida = db.Column(db.Text)
    criterio_idoneidad = db.Column(db.Text)

    apartado = db.relationship("Iso9001Apartado", back_populates="reactivos")
    respuestas = db.relationship("Iso9001Respuesta", back_populates="reactivo")

    __table_args__ = (
        UniqueConstraint("apartado_id", "orden", name="uq_iso9001_reactivo_apartado_orden"),
        UniqueConstraint("apartado_id", "numero", name="uq_iso9001_reactivo_apartado_numero"),
    )

    @property
    def codigo(self) -> str:
        return f"{self.apartado.codigo}.{self.numero}"


class Iso9001Ciclo(TimestampMixin, db.Model):
    __tablename__ = "iso9001_ciclo"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(180), unique=True, nullable=False)
    descripcion = db.Column(db.Text)
    estado = db.Column(db.String(20), default="borrador", nullable=False)
    fecha_inicio = db.Column(db.Date, nullable=False)
    fecha_cierre = db.Column(db.Date, nullable=False)
    version_id = db.Column(db.Integer, db.ForeignKey("iso9001_cuestionario_version.id"), nullable=False)
    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuario.id"))

    version = db.relationship("Iso9001CuestionarioVersion", back_populates="ciclos")
    creado_por = db.relationship("Usuario", back_populates="iso9001_ciclos_creados", foreign_keys=[creado_por_id])
    evaluaciones = db.relationship(
        "Iso9001Evaluacion",
        back_populates="ciclo",
        cascade="all, delete-orphan",
        order_by="Iso9001Evaluacion.updated_at.desc()",
    )

    @property
    def esta_activo(self) -> bool:
        return self.estado == "activo"


class Iso9001Evaluacion(TimestampMixin, db.Model):
    __tablename__ = "iso9001_evaluacion"

    id = db.Column(db.Integer, primary_key=True)
    ciclo_id = db.Column(db.Integer, db.ForeignKey("iso9001_ciclo.id"), nullable=False)
    dependencia_id = db.Column(db.Integer, db.ForeignKey("dependencia.id"), nullable=False)
    revisor_id = db.Column(db.Integer, db.ForeignKey("usuario.id"))
    estado = db.Column(db.String(20), default="borrador", nullable=False)
    progreso = db.Column(db.Float, default=0.0, nullable=False)
    enviada_revision_at = db.Column(db.DateTime)
    cerrada_at = db.Column(db.DateTime)

    ciclo = db.relationship("Iso9001Ciclo", back_populates="evaluaciones")
    dependencia = db.relationship("Dependencia", back_populates="iso9001_evaluaciones")
    revisor = db.relationship("Usuario", back_populates="iso9001_revisiones", foreign_keys=[revisor_id])
    asignaciones = db.relationship(
        "Iso9001Asignacion",
        back_populates="evaluacion",
        cascade="all, delete-orphan",
    )
    respuestas = db.relationship(
        "Iso9001Respuesta",
        back_populates="evaluacion",
        cascade="all, delete-orphan",
    )
    observaciones = db.relationship(
        "Iso9001ObservacionRevision",
        back_populates="evaluacion",
        cascade="all, delete-orphan",
        order_by="Iso9001ObservacionRevision.created_at.desc()",
    )

    __table_args__ = (
        UniqueConstraint("ciclo_id", "dependencia_id", name="uq_iso9001_evaluacion_ciclo_dependencia"),
    )

    @property
    def editable(self) -> bool:
        return self.estado in {"borrador", "en_captura", "devuelta"} and self.ciclo.esta_activo

    @property
    def responsable(self):
        assignment = next((item for item in self.asignaciones if item.tipo == "captura"), None)
        return assignment.usuario if assignment else None


class Iso9001Asignacion(TimestampMixin, db.Model):
    __tablename__ = "iso9001_asignacion"

    id = db.Column(db.Integer, primary_key=True)
    evaluacion_id = db.Column(db.Integer, db.ForeignKey("iso9001_evaluacion.id"), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    tipo = db.Column(db.String(30), default="captura", nullable=False)

    evaluacion = db.relationship("Iso9001Evaluacion", back_populates="asignaciones")
    usuario = db.relationship("Usuario", back_populates="iso9001_asignaciones", foreign_keys=[usuario_id])

    __table_args__ = (
        UniqueConstraint("evaluacion_id", "usuario_id", "tipo", name="uq_iso9001_asignacion_usuario_tipo"),
    )


class Iso9001Respuesta(TimestampMixin, db.Model):
    __tablename__ = "iso9001_respuesta"

    id = db.Column(db.Integer, primary_key=True)
    evaluacion_id = db.Column(db.Integer, db.ForeignKey("iso9001_evaluacion.id"), nullable=False)
    reactivo_id = db.Column(db.Integer, db.ForeignKey("iso9001_reactivo.id"), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    calificacion = db.Column(db.String(12), nullable=False)
    valor = db.Column(db.Integer)
    observacion = db.Column(db.Text)

    evaluacion = db.relationship("Iso9001Evaluacion", back_populates="respuestas")
    reactivo = db.relationship("Iso9001Reactivo", back_populates="respuestas")
    usuario = db.relationship("Usuario", back_populates="iso9001_respuestas", foreign_keys=[usuario_id])
    evidencias = db.relationship(
        "Iso9001Evidencia",
        back_populates="respuesta",
        cascade="all, delete-orphan",
        order_by="Iso9001Evidencia.created_at.desc()",
    )

    __table_args__ = (
        UniqueConstraint("evaluacion_id", "reactivo_id", name="uq_iso9001_respuesta_evaluacion_reactivo"),
    )


class Iso9001Evidencia(TimestampMixin, db.Model):
    __tablename__ = "iso9001_evidencia"

    id = db.Column(db.Integer, primary_key=True)
    respuesta_id = db.Column(db.Integer, db.ForeignKey("iso9001_respuesta.id"), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    archivo_nombre_original = db.Column(db.String(255), nullable=False)
    archivo_guardado = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(120), nullable=False)
    tamano_bytes = db.Column(db.Integer, nullable=False)
    activo = db.Column(db.Boolean, default=True, nullable=False)

    respuesta = db.relationship("Iso9001Respuesta", back_populates="evidencias")
    usuario = db.relationship("Usuario", back_populates="iso9001_evidencias", foreign_keys=[usuario_id])


class Iso9001ObservacionRevision(TimestampMixin, db.Model):
    __tablename__ = "iso9001_observacion_revision"

    id = db.Column(db.Integer, primary_key=True)
    evaluacion_id = db.Column(db.Integer, db.ForeignKey("iso9001_evaluacion.id"), nullable=False)
    autor_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    accion = db.Column(db.String(20), nullable=False)
    comentario = db.Column(db.Text, nullable=False)

    evaluacion = db.relationship("Iso9001Evaluacion", back_populates="observaciones")
    autor = db.relationship("Usuario", back_populates="iso9001_observaciones", foreign_keys=[autor_id])


class Evaluacion(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    periodo_id = db.Column(db.Integer, db.ForeignKey("periodo_evaluacion.id"), nullable=False)
    dependencia_id = db.Column(db.Integer, db.ForeignKey("dependencia.id"), nullable=False)
    revisor_id = db.Column(db.Integer, db.ForeignKey("usuario.id"))
    estado = db.Column(db.String(20), default="borrador", nullable=False)
    enviada_revision_at = db.Column(db.DateTime)
    aprobada_at = db.Column(db.DateTime)
    cerrada_at = db.Column(db.DateTime)

    periodo = db.relationship("PeriodoEvaluacion", back_populates="evaluaciones")
    dependencia = db.relationship("Dependencia", back_populates="evaluaciones")
    revisor = db.relationship("Usuario", back_populates="evaluaciones_revisadas")
    respuestas = db.relationship(
        "Respuesta",
        back_populates="evaluacion",
        cascade="all, delete-orphan",
    )
    evidencias = db.relationship(
        "EvidenciaEje",
        back_populates="evaluacion",
        cascade="all, delete-orphan",
        order_by="EvidenciaEje.created_at.desc()",
    )
    observaciones = db.relationship(
        "ObservacionRevision",
        back_populates="evaluacion",
        cascade="all, delete-orphan",
        order_by="ObservacionRevision.created_at.desc()",
    )
    asignaciones = db.relationship(
        "EvaluacionAsignacion",
        back_populates="evaluacion",
        cascade="all, delete-orphan",
    )
    comentarios_eje = db.relationship(
        "ComentarioEje",
        back_populates="evaluacion",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("periodo_id", "dependencia_id", name="uq_evaluacion_periodo_dependencia"),
    )

    @property
    def editable(self) -> bool:
        return self.estado in {"borrador", "en_captura", "devuelta"}


class EvaluacionAsignacion(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    evaluacion_id = db.Column(db.Integer, db.ForeignKey("evaluacion.id"), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    area_id = db.Column(db.Integer, db.ForeignKey("area.id"))
    tipo = db.Column(db.String(30), default="captura", nullable=False)

    evaluacion = db.relationship("Evaluacion", back_populates="asignaciones")
    usuario = db.relationship("Usuario", back_populates="asignaciones")
    area = db.relationship("Area", back_populates="asignaciones")

    __table_args__ = (
        UniqueConstraint(
            "evaluacion_id",
            "usuario_id",
            "tipo",
            name="uq_asignacion_evaluacion_usuario_tipo",
        ),
    )


class Respuesta(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    evaluacion_id = db.Column(db.Integer, db.ForeignKey("evaluacion.id"), nullable=False)
    reactivo_version_id = db.Column(
        db.Integer,
        db.ForeignKey("reactivo_version.id"),
        nullable=False,
    )
    area_id = db.Column(db.Integer, db.ForeignKey("area.id"))
    usuario_captura_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    valor = db.Column(db.Integer, nullable=False)
    comentario = db.Column(db.Text)

    evaluacion = db.relationship("Evaluacion", back_populates="respuestas")
    reactivo_version = db.relationship("ReactivoVersion", back_populates="respuestas")
    area = db.relationship("Area", back_populates="respuestas")
    usuario_captura = db.relationship("Usuario", back_populates="respuestas_capturadas")

    __table_args__ = (
        UniqueConstraint(
            "evaluacion_id",
            "reactivo_version_id",
            name="uq_respuesta_evaluacion_reactivo",
        ),
    )


class EvidenciaEje(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    evaluacion_id = db.Column(db.Integer, db.ForeignKey("evaluacion.id"), nullable=False)
    eje_version_id = db.Column(db.Integer, db.ForeignKey("eje_version.id"), nullable=False)
    area_id = db.Column(db.Integer, db.ForeignKey("area.id"))
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    version = db.Column(db.Integer, default=1, nullable=False)
    archivo_nombre_original = db.Column(db.String(255), nullable=False)
    archivo_guardado = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(120), nullable=False)
    tamano_bytes = db.Column(db.Integer, nullable=False)
    reemplaza_id = db.Column(db.Integer, db.ForeignKey("evidencia_eje.id"))
    activo = db.Column(db.Boolean, default=True, nullable=False)

    evaluacion = db.relationship("Evaluacion", back_populates="evidencias")
    eje_version = db.relationship("EjeVersion", back_populates="evidencias")
    usuario = db.relationship("Usuario", back_populates="evidencias_subidas")
    area = db.relationship("Area")
    reemplaza = db.relationship("EvidenciaEje", remote_side=[id], uselist=False)


class ComentarioEje(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    evaluacion_id = db.Column(db.Integer, db.ForeignKey("evaluacion.id"), nullable=False)
    eje_version_id = db.Column(db.Integer, db.ForeignKey("eje_version.id"), nullable=False)
    area_id = db.Column(db.Integer, db.ForeignKey("area.id"))
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    comentario = db.Column(db.Text)

    evaluacion = db.relationship("Evaluacion", back_populates="comentarios_eje")
    eje_version = db.relationship("EjeVersion", back_populates="comentarios")
    area = db.relationship("Area")
    usuario = db.relationship("Usuario", back_populates="comentarios_eje")

    __table_args__ = (
        UniqueConstraint(
            "evaluacion_id",
            "eje_version_id",
            name="uq_comentario_eje_evaluacion",
        ),
    )


class ObservacionRevision(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    evaluacion_id = db.Column(db.Integer, db.ForeignKey("evaluacion.id"), nullable=False)
    eje_version_id = db.Column(db.Integer, db.ForeignKey("eje_version.id"))
    autor_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    comentario = db.Column(db.Text, nullable=False)
    atendida = db.Column(db.Boolean, default=False, nullable=False)
    atendida_at = db.Column(db.DateTime)

    evaluacion = db.relationship("Evaluacion", back_populates="observaciones")
    eje_version = db.relationship("EjeVersion", back_populates="observaciones")
    autor = db.relationship("Usuario", back_populates="observaciones")


class Notificacion(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    tipo = db.Column(db.String(40), nullable=False)
    mensaje = db.Column(db.String(255), nullable=False)
    enlace = db.Column(db.String(255))
    leida = db.Column(db.Boolean, default=False, nullable=False)

    usuario = db.relationship("Usuario", back_populates="notificaciones")


class LiveReactivoTemplate(TimestampMixin, db.Model):
    __tablename__ = "live_reactivo_template"

    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(40), nullable=False, index=True)
    titulo = db.Column(db.String(180), nullable=False)
    prompt = db.Column(db.Text, nullable=False)
    config_json = db.Column(json_payload_type(), nullable=False, default=dict)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuario.id"))

    creado_por = db.relationship("Usuario", back_populates="live_templates", foreign_keys=[creado_por_id])
    activities = db.relationship("LiveActivity", back_populates="template")


class LiveSession(TimestampMixin, db.Model):
    __tablename__ = "live_session"

    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(180), nullable=False)
    descripcion = db.Column(db.Text)
    code = db.Column(db.String(12), nullable=False, unique=True, index=True)
    mode = db.Column(db.String(20), nullable=False, default="guided")
    estado = db.Column(db.String(20), nullable=False, default="draft")
    active_activity_id = db.Column(db.Integer)
    presentador_id = db.Column(db.Integer, db.ForeignKey("usuario.id"))
    config_json = db.Column(json_payload_type(), nullable=False, default=dict)
    opened_at = db.Column(db.DateTime)
    closed_at = db.Column(db.DateTime)

    presentador = db.relationship("Usuario", back_populates="live_sessions_presentadas", foreign_keys=[presentador_id])
    activities = db.relationship(
        "LiveActivity",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="LiveActivity.orden",
    )
    participants = db.relationship(
        "LiveParticipant",
        back_populates="session",
        cascade="all, delete-orphan",
    )
    responses = db.relationship(
        "LiveResponse",
        back_populates="session",
        cascade="all, delete-orphan",
    )


class LiveActivity(TimestampMixin, db.Model):
    __tablename__ = "live_activity"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("live_session.id"), nullable=False)
    template_id = db.Column(db.Integer, db.ForeignKey("live_reactivo_template.id"))
    orden = db.Column(db.Integer, nullable=False)
    tipo = db.Column(db.String(40), nullable=False, index=True)
    titulo = db.Column(db.String(180), nullable=False)
    prompt = db.Column(db.Text, nullable=False)
    estado = db.Column(db.String(20), nullable=False, default="draft")
    config_json = db.Column(json_payload_type(), nullable=False, default=dict)
    payload_json = db.Column(json_payload_type(), nullable=False, default=dict)
    opened_at = db.Column(db.DateTime)
    closed_at = db.Column(db.DateTime)

    session = db.relationship("LiveSession", back_populates="activities")
    template = db.relationship("LiveReactivoTemplate", back_populates="activities")
    responses = db.relationship(
        "LiveResponse",
        back_populates="activity",
        cascade="all, delete-orphan",
        order_by="LiveResponse.created_at",
    )

    __table_args__ = (
        UniqueConstraint("session_id", "orden", name="uq_live_activity_session_order"),
    )


class LiveParticipant(TimestampMixin, db.Model):
    __tablename__ = "live_participant"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("live_session.id"), nullable=False)
    token = db.Column(db.String(120), nullable=False)
    ultima_actividad_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    connected = db.Column(db.Boolean, nullable=False, default=False)

    session = db.relationship("LiveSession", back_populates="participants")
    responses = db.relationship(
        "LiveResponse",
        back_populates="participant",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("session_id", "token", name="uq_live_participant_session_token"),
    )


class LiveResponse(TimestampMixin, db.Model):
    __tablename__ = "live_response"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("live_session.id"), nullable=False)
    activity_id = db.Column(db.Integer, db.ForeignKey("live_activity.id"), nullable=False)
    participant_id = db.Column(db.Integer, db.ForeignKey("live_participant.id"), nullable=False)
    response_key = db.Column(db.String(80), nullable=False)
    payload_json = db.Column(json_payload_type(), nullable=False, default=dict)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    session = db.relationship("LiveSession", back_populates="responses")
    activity = db.relationship("LiveActivity", back_populates="responses")
    participant = db.relationship("LiveParticipant", back_populates="responses")

    __table_args__ = (
        UniqueConstraint("activity_id", "participant_id", "response_key", name="uq_live_response_activity_participant_key"),
    )


class SesionPlataforma(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    session_key = db.Column(db.String(120), unique=True, nullable=False, index=True)
    ip = db.Column(db.String(80))
    user_agent = db.Column(db.String(512))
    iniciada_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    ultima_actividad_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    cerrada_at = db.Column(db.DateTime)
    activa = db.Column(db.Boolean, default=True, nullable=False)

    usuario = db.relationship("Usuario", back_populates="sesiones")
    actividades = db.relationship(
        "ActividadPlataforma",
        back_populates="sesion",
        cascade="all, delete-orphan",
        order_by="ActividadPlataforma.created_at.desc()",
    )


class ActividadPlataforma(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sesion_id = db.Column(db.Integer, db.ForeignKey("sesion_plataforma.id"))
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"))
    tipo = db.Column(db.String(80), nullable=False, index=True)
    ruta = db.Column(db.String(255))
    metodo = db.Column(db.String(20))
    entidad_tipo = db.Column(db.String(80))
    entidad_id = db.Column(db.Integer)
    metadata_json = db.Column(db.JSON)

    sesion = db.relationship("SesionPlataforma", back_populates="actividades")
    usuario = db.relationship("Usuario", back_populates="actividades")
