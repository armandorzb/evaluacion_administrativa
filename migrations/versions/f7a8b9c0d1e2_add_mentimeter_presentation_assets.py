"""add Mentimeter presentation assets

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-07-12 00:30:00.000000

The standalone Mentimeter service normally creates its own schema with
``db.create_all``.  This migration intentionally becomes a no-op on municipal
databases where that standalone ``sessions`` table is not installed, while
remaining safe for deployments that do keep both schemas in one database.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


TABLE_NAME = "presentation_assets"


def upgrade():
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "sessions" not in tables or TABLE_NAME in tables:
        return

    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=120), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("alt_text", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_presentation_assets_session_id"), TABLE_NAME, ["session_id"], unique=False)
    op.create_index(op.f("ix_presentation_assets_storage_key"), TABLE_NAME, ["storage_key"], unique=True)


def downgrade():
    inspector = sa.inspect(op.get_bind())
    if TABLE_NAME not in set(inspector.get_table_names()):
        return
    op.drop_index(op.f("ix_presentation_assets_storage_key"), table_name=TABLE_NAME)
    op.drop_index(op.f("ix_presentation_assets_session_id"), table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
