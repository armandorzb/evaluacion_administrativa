"""add module access flags to usuario

Revision ID: e3f9a8b4c2d1
Revises: c1a5d9e7b204
Create Date: 2026-03-29 16:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e3f9a8b4c2d1"
down_revision = "c1a5d9e7b204"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("usuario", sa.Column("acceso_diagnostico", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("usuario", sa.Column("acceso_bienestar", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute(
        """
        UPDATE usuario
        SET acceso_diagnostico = 1,
            acceso_bienestar = CASE
                WHEN rol IN ('administrador', 'consulta') THEN 1
                ELSE 0
            END
        """
    )
    op.alter_column("usuario", "acceso_diagnostico", server_default=None)
    op.alter_column("usuario", "acceso_bienestar", server_default=None)


def downgrade():
    op.drop_column("usuario", "acceso_bienestar")
    op.drop_column("usuario", "acceso_diagnostico")
