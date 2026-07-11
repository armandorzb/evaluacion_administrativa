"""add iso45001 module

Revision ID: c4f5e6a7b8d9
Revises: b8e2f4a6c9d0
Create Date: 2026-07-11 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c4f5e6a7b8d9"
down_revision = "b8e2f4a6c9d0"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    usuario_columns = {
        column["name"]
        for column in sa.inspect(bind).get_columns("usuario")
    }
    # SQLite applies DDL outside a transaction.  If a deployment is interrupted
    # after this column is added, a retry must continue safely from that state.
    if "acceso_iso45001" not in usuario_columns:
        op.add_column(
            "usuario",
            sa.Column("acceso_iso45001", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    op.execute(
        """
        UPDATE usuario
        SET acceso_iso45001 = CASE
            WHEN rol = 'administrador' THEN TRUE
            ELSE FALSE
        END
        """
    )
    # SQLite cannot drop a column default in place.  Retaining the default is
    # harmless there and avoids an invalid ALTER TABLE on deployment.
    if bind.dialect.name != "sqlite":
        op.alter_column("usuario", "acceso_iso45001", server_default=None)

    op.create_table(
        "iso45001_cuestionario_version",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("nombre", sa.String(length=180), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("norma", sa.String(length=100), nullable=False),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("publicado_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_iso45001_cuestionario_version_slug"),
        "iso45001_cuestionario_version",
        ["slug"],
        unique=True,
    )

    op.create_table(
        "iso45001_clausula",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column("numero", sa.String(length=10), nullable=False),
        sa.Column("nombre", sa.String(length=180), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["iso45001_cuestionario_version.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_id", "numero", name="uq_iso45001_clausula_version_numero"),
    )

    op.create_table(
        "iso45001_apartado",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("clausula_id", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(length=20), nullable=False),
        sa.Column("nombre", sa.String(length=220), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["clausula_id"], ["iso45001_clausula.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("clausula_id", "codigo", name="uq_iso45001_apartado_clausula_codigo"),
    )

    op.create_table(
        "iso45001_documento_requerido",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(length=40), nullable=False),
        sa.Column("apartado", sa.String(length=40), nullable=False),
        sa.Column("clasificacion", sa.String(length=20), nullable=False),
        sa.Column("nombre", sa.String(length=255), nullable=False),
        sa.Column("contenido_minimo", sa.Text(), nullable=True),
        sa.Column("criticidad", sa.String(length=30), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["iso45001_cuestionario_version.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_id", "codigo", name="uq_iso45001_documento_version_codigo"),
        sa.UniqueConstraint("version_id", "orden", name="uq_iso45001_documento_version_orden"),
    )

    op.create_table(
        "iso45001_reactivo",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("apartado_id", sa.Integer(), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(length=40), nullable=False),
        sa.Column("tema", sa.String(length=255), nullable=True),
        sa.Column("criticidad", sa.String(length=30), nullable=False),
        sa.Column("es_enmienda_2024", sa.Boolean(), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("evidencia_sugerida", sa.Text(), nullable=True),
        sa.Column("criterio_idoneidad", sa.Text(), nullable=True),
        sa.Column("requiere_documento", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["apartado_id"], ["iso45001_apartado.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("apartado_id", "orden", name="uq_iso45001_reactivo_apartado_orden"),
        sa.UniqueConstraint("apartado_id", "numero", name="uq_iso45001_reactivo_apartado_numero"),
    )

    op.create_table(
        "iso45001_reactivo_documento_requerido",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reactivo_id", sa.Integer(), nullable=False),
        sa.Column("documento_requerido_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["documento_requerido_id"], ["iso45001_documento_requerido.id"]),
        sa.ForeignKeyConstraint(["reactivo_id"], ["iso45001_reactivo.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reactivo_id", "documento_requerido_id", name="uq_iso45001_reactivo_documento"),
    )

    op.create_table(
        "iso45001_ciclo",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=180), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("fecha_inicio", sa.Date(), nullable=False),
        sa.Column("fecha_cierre", sa.Date(), nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column("creado_por_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["creado_por_id"], ["usuario.id"]),
        sa.ForeignKeyConstraint(["version_id"], ["iso45001_cuestionario_version.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nombre"),
    )

    op.create_table(
        "iso45001_evaluacion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ciclo_id", sa.Integer(), nullable=False),
        sa.Column("dependencia_id", sa.Integer(), nullable=False),
        sa.Column("revisor_id", sa.Integer(), nullable=True),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("progreso", sa.Float(), nullable=False),
        sa.Column("enviada_revision_at", sa.DateTime(), nullable=True),
        sa.Column("cerrada_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["ciclo_id"], ["iso45001_ciclo.id"]),
        sa.ForeignKeyConstraint(["dependencia_id"], ["dependencia.id"]),
        sa.ForeignKeyConstraint(["revisor_id"], ["usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ciclo_id", "dependencia_id", name="uq_iso45001_evaluacion_ciclo_dependencia"),
    )

    op.create_table(
        "iso45001_asignacion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("evaluacion_id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["evaluacion_id"], ["iso45001_evaluacion.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("evaluacion_id", "usuario_id", "tipo", name="uq_iso45001_asignacion_usuario_tipo"),
    )

    op.create_table(
        "iso45001_respuesta",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("evaluacion_id", sa.Integer(), nullable=False),
        sa.Column("reactivo_id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("calificacion", sa.String(length=12), nullable=False),
        sa.Column("valor", sa.Integer(), nullable=True),
        sa.Column("observacion", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["evaluacion_id"], ["iso45001_evaluacion.id"]),
        sa.ForeignKeyConstraint(["reactivo_id"], ["iso45001_reactivo.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("evaluacion_id", "reactivo_id", name="uq_iso45001_respuesta_evaluacion_reactivo"),
    )

    op.create_table(
        "iso45001_evidencia",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("respuesta_id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("archivo_nombre_original", sa.String(length=255), nullable=False),
        sa.Column("archivo_guardado", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("tamano_bytes", sa.Integer(), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["respuesta_id"], ["iso45001_respuesta.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "iso45001_observacion_revision",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("evaluacion_id", sa.Integer(), nullable=False),
        sa.Column("autor_id", sa.Integer(), nullable=False),
        sa.Column("accion", sa.String(length=20), nullable=False),
        sa.Column("comentario", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["autor_id"], ["usuario.id"]),
        sa.ForeignKeyConstraint(["evaluacion_id"], ["iso45001_evaluacion.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("iso45001_observacion_revision")
    op.drop_table("iso45001_evidencia")
    op.drop_table("iso45001_respuesta")
    op.drop_table("iso45001_asignacion")
    op.drop_table("iso45001_evaluacion")
    op.drop_table("iso45001_ciclo")
    op.drop_table("iso45001_reactivo_documento_requerido")
    op.drop_table("iso45001_reactivo")
    op.drop_table("iso45001_documento_requerido")
    op.drop_table("iso45001_apartado")
    op.drop_table("iso45001_clausula")
    op.drop_index(op.f("ix_iso45001_cuestionario_version_slug"), table_name="iso45001_cuestionario_version")
    op.drop_table("iso45001_cuestionario_version")
    op.drop_column("usuario", "acceso_iso45001")
