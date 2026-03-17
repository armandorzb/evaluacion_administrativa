"""add monitoring and axis comments

Revision ID: d4b2e7c1a901
Revises: 828dfa848ed7
Create Date: 2026-03-16 18:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d4b2e7c1a901"
down_revision = "828dfa848ed7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "comentario_eje",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("evaluacion_id", sa.Integer(), nullable=False),
        sa.Column("eje_version_id", sa.Integer(), nullable=False),
        sa.Column("area_id", sa.Integer(), nullable=True),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("comentario", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["area_id"], ["area.id"]),
        sa.ForeignKeyConstraint(["eje_version_id"], ["eje_version.id"]),
        sa.ForeignKeyConstraint(["evaluacion_id"], ["evaluacion.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("evaluacion_id", "eje_version_id", name="uq_comentario_eje_evaluacion"),
    )
    op.create_table(
        "sesion_plataforma",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("session_key", sa.String(length=120), nullable=False),
        sa.Column("ip", sa.String(length=80), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("iniciada_at", sa.DateTime(), nullable=False),
        sa.Column("ultima_actividad_at", sa.DateTime(), nullable=False),
        sa.Column("cerrada_at", sa.DateTime(), nullable=True),
        sa.Column("activa", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_key"),
    )
    op.create_index(op.f("ix_sesion_plataforma_session_key"), "sesion_plataforma", ["session_key"], unique=False)
    op.create_table(
        "actividad_plataforma",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sesion_id", sa.Integer(), nullable=True),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("tipo", sa.String(length=80), nullable=False),
        sa.Column("ruta", sa.String(length=255), nullable=True),
        sa.Column("metodo", sa.String(length=20), nullable=True),
        sa.Column("entidad_tipo", sa.String(length=80), nullable=True),
        sa.Column("entidad_id", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["sesion_id"], ["sesion_plataforma.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_actividad_plataforma_tipo"), "actividad_plataforma", ["tipo"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_actividad_plataforma_tipo"), table_name="actividad_plataforma")
    op.drop_table("actividad_plataforma")
    op.drop_index(op.f("ix_sesion_plataforma_session_key"), table_name="sesion_plataforma")
    op.drop_table("sesion_plataforma")
    op.drop_table("comentario_eje")
