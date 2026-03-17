"""add active flag to area

Revision ID: f2a1c9b8d0e4
Revises: d4b2e7c1a901
Create Date: 2026-03-16 23:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f2a1c9b8d0e4"
down_revision = "d4b2e7c1a901"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("area", sa.Column("activa", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.alter_column("area", "activa", server_default=None)


def downgrade():
    op.drop_column("area", "activa")
