"""add ISO 45001 documentary coverage controls

Revision ID: d5e6f7a8b9c0
Revises: c4f5e6a7b8d9
Create Date: 2026-07-11 00:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d5e6f7a8b9c0"
down_revision = "c4f5e6a7b8d9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "iso45001_control_evidencia",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(length=40), nullable=False),
        sa.Column("tipo", sa.String(length=30), nullable=False),
        sa.Column("clausula", sa.String(length=10), nullable=False),
        sa.Column("apartado", sa.String(length=40), nullable=False),
        sa.Column("clasificacion", sa.String(length=40), nullable=False),
        sa.Column("nombre", sa.String(length=255), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("contenido_minimo", sa.Text(), nullable=True),
        sa.Column("evidencia_sugerida", sa.Text(), nullable=True),
        sa.Column("criticidad", sa.String(length=30), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["iso45001_cuestionario_version.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "version_id",
            "codigo",
            name="uq_iso45001_control_evidencia_version_codigo",
        ),
        sa.UniqueConstraint(
            "version_id",
            "orden",
            name="uq_iso45001_control_evidencia_version_orden",
        ),
    )
    op.create_table(
        "iso45001_control_evidencia_punto",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("control_evidencia_id", sa.Integer(), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["control_evidencia_id"], ["iso45001_control_evidencia.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "control_evidencia_id",
            "orden",
            name="uq_iso45001_control_evidencia_punto_orden",
        ),
    )
    op.create_table(
        "iso45001_control_evidencia_reactivo",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("control_evidencia_id", sa.Integer(), nullable=False),
        sa.Column("reactivo_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["control_evidencia_id"], ["iso45001_control_evidencia.id"]),
        sa.ForeignKeyConstraint(["reactivo_id"], ["iso45001_reactivo.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "control_evidencia_id",
            "reactivo_id",
            name="uq_iso45001_control_evidencia_reactivo",
        ),
    )
    op.create_table(
        "iso45001_evaluacion_control_evidencia",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("evaluacion_id", sa.Integer(), nullable=False),
        sa.Column("control_evidencia_id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("estado", sa.String(length=12), nullable=False),
        sa.Column("observacion", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["control_evidencia_id"], ["iso45001_control_evidencia.id"]),
        sa.ForeignKeyConstraint(["evaluacion_id"], ["iso45001_evaluacion.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "evaluacion_id",
            "control_evidencia_id",
            name="uq_iso45001_evaluacion_control_evidencia",
        ),
    )
    op.create_table(
        "iso45001_evaluacion_control_evidencia_punto",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("evaluacion_control_evidencia_id", sa.Integer(), nullable=False),
        sa.Column("control_evidencia_punto_id", sa.Integer(), nullable=False),
        sa.Column("cubierto", sa.Boolean(), nullable=False),
        sa.Column("observacion", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["control_evidencia_punto_id"],
            ["iso45001_control_evidencia_punto.id"],
        ),
        sa.ForeignKeyConstraint(
            ["evaluacion_control_evidencia_id"],
            ["iso45001_evaluacion_control_evidencia.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "evaluacion_control_evidencia_id",
            "control_evidencia_punto_id",
            name="uq_iso45001_evaluacion_control_evidencia_punto",
        ),
    )
    op.create_table(
        "iso45001_evidencia_documental",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("evaluacion_id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("archivo_nombre_original", sa.String(length=255), nullable=False),
        sa.Column("archivo_guardado", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("tamano_bytes", sa.Integer(), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["evaluacion_id"], ["iso45001_evaluacion.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "iso45001_evidencia_documental_control",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("evidencia_documental_id", sa.Integer(), nullable=False),
        sa.Column("evaluacion_control_evidencia_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["evaluacion_control_evidencia_id"],
            ["iso45001_evaluacion_control_evidencia.id"],
        ),
        sa.ForeignKeyConstraint(
            ["evidencia_documental_id"],
            ["iso45001_evidencia_documental.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "evidencia_documental_id",
            "evaluacion_control_evidencia_id",
            name="uq_iso45001_evidencia_documental_control",
        ),
    )


def downgrade():
    op.drop_table("iso45001_evidencia_documental_control")
    op.drop_table("iso45001_evidencia_documental")
    op.drop_table("iso45001_evaluacion_control_evidencia_punto")
    op.drop_table("iso45001_evaluacion_control_evidencia")
    op.drop_table("iso45001_control_evidencia_reactivo")
    op.drop_table("iso45001_control_evidencia_punto")
    op.drop_table("iso45001_control_evidencia")
