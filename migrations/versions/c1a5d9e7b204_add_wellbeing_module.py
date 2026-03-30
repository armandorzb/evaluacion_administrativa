"""add wellbeing module

Revision ID: c1a5d9e7b204
Revises: 7c3d4ef2a1b0
Create Date: 2026-03-29 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c1a5d9e7b204"
down_revision = "7c3d4ef2a1b0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bienestar_pregunta",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("dimension", sa.String(length=100), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("opciones", sa.JSON(), nullable=False),
        sa.Column("activa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("orden"),
    )
    op.create_table(
        "bienestar_encuesta",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("hash_id", sa.String(length=50), nullable=False),
        sa.Column("estrato", sa.String(length=10), nullable=False),
        sa.Column("iibp", sa.Float(), nullable=True),
        sa.Column("ivsp", sa.Float(), nullable=True),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("ultima_pregunta", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completada_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hash_id"),
    )
    op.create_index(op.f("ix_bienestar_encuesta_hash_id"), "bienestar_encuesta", ["hash_id"], unique=True)
    op.create_table(
        "bienestar_respuesta",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("encuesta_id", sa.Integer(), nullable=False),
        sa.Column("pregunta_id", sa.Integer(), nullable=False),
        sa.Column("dimension", sa.String(length=100), nullable=False),
        sa.Column("valor", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["encuesta_id"], ["bienestar_encuesta.id"]),
        sa.ForeignKeyConstraint(["pregunta_id"], ["bienestar_pregunta.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("encuesta_id", "pregunta_id", name="uq_bienestar_encuesta_pregunta"),
    )


def downgrade():
    op.drop_table("bienestar_respuesta")
    op.drop_index(op.f("ix_bienestar_encuesta_hash_id"), table_name="bienestar_encuesta")
    op.drop_table("bienestar_encuesta")
    op.drop_table("bienestar_pregunta")
