"""add campaigns and assignments

Revision ID: 7c3d4ef2a1b0
Revises: f2a1c9b8d0e4
Create Date: 2026-03-16 19:05:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7c3d4ef2a1b0"
down_revision = "f2a1c9b8d0e4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "campana_cuestionario",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=160), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("fecha_apertura", sa.Date(), nullable=False),
        sa.Column("fecha_limite", sa.Date(), nullable=False),
        sa.Column("cuestionario_version_id", sa.Integer(), nullable=False),
        sa.Column("creado_por_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["creado_por_id"], ["usuario.id"]),
        sa.ForeignKeyConstraint(["cuestionario_version_id"], ["cuestionario_version.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nombre"),
    )
    op.create_table(
        "asignacion_cuestionario",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campana_id", sa.Integer(), nullable=False),
        sa.Column("target_type", sa.String(length=20), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("dependencia_id", sa.Integer(), nullable=True),
        sa.Column("respondente_id", sa.Integer(), nullable=True),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("progreso", sa.Float(), nullable=False),
        sa.Column("fecha_inicio", sa.DateTime(), nullable=True),
        sa.Column("fecha_envio", sa.DateTime(), nullable=True),
        sa.Column("cerrada_at", sa.DateTime(), nullable=True),
        sa.Column("ultima_actividad_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["campana_id"], ["campana_cuestionario.id"]),
        sa.ForeignKeyConstraint(["dependencia_id"], ["dependencia.id"]),
        sa.ForeignKeyConstraint(["respondente_id"], ["usuario.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campana_id",
            "target_type",
            "usuario_id",
            "dependencia_id",
            name="uq_campana_target_asignacion",
        ),
    )
    op.create_table(
        "respuesta_asignacion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("asignacion_id", sa.Integer(), nullable=False),
        sa.Column("reactivo_version_id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("valor", sa.Integer(), nullable=False),
        sa.Column("comentario", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["asignacion_id"], ["asignacion_cuestionario.id"]),
        sa.ForeignKeyConstraint(["reactivo_version_id"], ["reactivo_version.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "asignacion_id",
            "reactivo_version_id",
            name="uq_respuesta_asignacion_reactivo",
        ),
    )
    op.create_table(
        "soporte_seccion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("asignacion_id", sa.Integer(), nullable=False),
        sa.Column("eje_version_id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("comentario", sa.Text(), nullable=True),
        sa.Column("archivo_nombre_original", sa.String(length=255), nullable=True),
        sa.Column("archivo_guardado", sa.String(length=255), nullable=True),
        sa.Column("mime_type", sa.String(length=120), nullable=True),
        sa.Column("tamano_bytes", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["asignacion_id"], ["asignacion_cuestionario.id"]),
        sa.ForeignKeyConstraint(["eje_version_id"], ["eje_version.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "asignacion_id",
            "eje_version_id",
            name="uq_soporte_asignacion_eje",
        ),
    )


def downgrade():
    op.drop_table("soporte_seccion")
    op.drop_table("respuesta_asignacion")
    op.drop_table("asignacion_cuestionario")
    op.drop_table("campana_cuestionario")
