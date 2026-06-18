"""add iso9001 module

Revision ID: a7d9c3e2f1b4
Revises: f6b1c2d3e4f5
Create Date: 2026-06-18 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a7d9c3e2f1b4"
down_revision = "f6b1c2d3e4f5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("usuario", sa.Column("acceso_iso9001", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute(
        """
        UPDATE usuario
        SET acceso_iso9001 = CASE
            WHEN rol = 'administrador' THEN 1
            ELSE 0
        END
        """
    )
    op.alter_column("usuario", "acceso_iso9001", server_default=None)

    op.create_table(
        "iso9001_cuestionario_version",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("nombre", sa.String(length=180), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("norma", sa.String(length=80), nullable=False),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("publicado_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_iso9001_cuestionario_version_slug"),
        "iso9001_cuestionario_version",
        ["slug"],
        unique=True,
    )

    op.create_table(
        "iso9001_clausula",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column("numero", sa.String(length=10), nullable=False),
        sa.Column("nombre", sa.String(length=180), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["iso9001_cuestionario_version.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_id", "numero", name="uq_iso9001_clausula_version_numero"),
    )

    op.create_table(
        "iso9001_apartado",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("clausula_id", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(length=20), nullable=False),
        sa.Column("nombre", sa.String(length=220), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["clausula_id"], ["iso9001_clausula.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("clausula_id", "codigo", name="uq_iso9001_apartado_clausula_codigo"),
    )

    op.create_table(
        "iso9001_reactivo",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("apartado_id", sa.Integer(), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("evidencia_sugerida", sa.Text(), nullable=True),
        sa.Column("criterio_idoneidad", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["apartado_id"], ["iso9001_apartado.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("apartado_id", "orden", name="uq_iso9001_reactivo_apartado_orden"),
        sa.UniqueConstraint("apartado_id", "numero", name="uq_iso9001_reactivo_apartado_numero"),
    )

    op.create_table(
        "iso9001_ciclo",
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
        sa.ForeignKeyConstraint(["version_id"], ["iso9001_cuestionario_version.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nombre"),
    )

    op.create_table(
        "iso9001_evaluacion",
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
        sa.ForeignKeyConstraint(["ciclo_id"], ["iso9001_ciclo.id"]),
        sa.ForeignKeyConstraint(["dependencia_id"], ["dependencia.id"]),
        sa.ForeignKeyConstraint(["revisor_id"], ["usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ciclo_id", "dependencia_id", name="uq_iso9001_evaluacion_ciclo_dependencia"),
    )

    op.create_table(
        "iso9001_asignacion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("evaluacion_id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["evaluacion_id"], ["iso9001_evaluacion.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("evaluacion_id", "usuario_id", "tipo", name="uq_iso9001_asignacion_usuario_tipo"),
    )

    op.create_table(
        "iso9001_respuesta",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("evaluacion_id", sa.Integer(), nullable=False),
        sa.Column("reactivo_id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("calificacion", sa.String(length=12), nullable=False),
        sa.Column("valor", sa.Integer(), nullable=True),
        sa.Column("observacion", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["evaluacion_id"], ["iso9001_evaluacion.id"]),
        sa.ForeignKeyConstraint(["reactivo_id"], ["iso9001_reactivo.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("evaluacion_id", "reactivo_id", name="uq_iso9001_respuesta_evaluacion_reactivo"),
    )

    op.create_table(
        "iso9001_evidencia",
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
        sa.ForeignKeyConstraint(["respuesta_id"], ["iso9001_respuesta.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "iso9001_observacion_revision",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("evaluacion_id", sa.Integer(), nullable=False),
        sa.Column("autor_id", sa.Integer(), nullable=False),
        sa.Column("accion", sa.String(length=20), nullable=False),
        sa.Column("comentario", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["autor_id"], ["usuario.id"]),
        sa.ForeignKeyConstraint(["evaluacion_id"], ["iso9001_evaluacion.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("iso9001_observacion_revision")
    op.drop_table("iso9001_evidencia")
    op.drop_table("iso9001_respuesta")
    op.drop_table("iso9001_asignacion")
    op.drop_table("iso9001_evaluacion")
    op.drop_table("iso9001_ciclo")
    op.drop_table("iso9001_reactivo")
    op.drop_table("iso9001_apartado")
    op.drop_table("iso9001_clausula")
    op.drop_index(op.f("ix_iso9001_cuestionario_version_slug"), table_name="iso9001_cuestionario_version")
    op.drop_table("iso9001_cuestionario_version")
    op.drop_column("usuario", "acceso_iso9001")
