"""add wellbeing profile question type

Revision ID: f6b1c2d3e4f5
Revises: e3f9a8b4c2d1
Create Date: 2026-03-29 22:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f6b1c2d3e4f5"
down_revision = "e3f9a8b4c2d1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "bienestar_pregunta",
        sa.Column("tipo_reactivo", sa.String(length=20), nullable=False, server_default="indicador"),
    )
    op.execute(
        """
        UPDATE bienestar_pregunta
        SET tipo_reactivo = CASE
            WHEN orden BETWEEN 36 AND 45 THEN 'perfil'
            ELSE 'indicador'
        END
        """
    )
    op.alter_column("bienestar_pregunta", "tipo_reactivo", server_default=None)


def downgrade():
    op.drop_column("bienestar_pregunta", "tipo_reactivo")
