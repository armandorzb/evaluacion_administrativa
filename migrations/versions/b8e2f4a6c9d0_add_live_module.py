"""add live module

Revision ID: b8e2f4a6c9d0
Revises: a7d9c3e2f1b4
Create Date: 2026-06-19 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "b8e2f4a6c9d0"
down_revision = "a7d9c3e2f1b4"
branch_labels = None
depends_on = None


json_payload = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade():
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    usuario_columns = {column["name"] for column in inspector.get_columns("usuario")} if "usuario" in tables else set()

    if "acceso_live" not in usuario_columns:
        op.add_column("usuario", sa.Column("acceso_live", sa.Boolean(), nullable=False, server_default=sa.false()))
        op.execute(
            """
            UPDATE usuario
            SET acceso_live = CASE
                WHEN rol = 'administrador' THEN 1
                ELSE 0
            END
            """
        )
        op.alter_column("usuario", "acceso_live", server_default=None)

    if "live_reactivo_template" not in tables:
        op.create_table(
            "live_reactivo_template",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tipo", sa.String(length=40), nullable=False),
            sa.Column("titulo", sa.String(length=180), nullable=False),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("config_json", json_payload, nullable=False),
            sa.Column("activo", sa.Boolean(), nullable=False),
            sa.Column("creado_por_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["creado_por_id"], ["usuario.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_live_reactivo_template_tipo"), "live_reactivo_template", ["tipo"], unique=False)

    if "live_session" not in tables:
        op.create_table(
            "live_session",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("titulo", sa.String(length=180), nullable=False),
            sa.Column("descripcion", sa.Text(), nullable=True),
            sa.Column("code", sa.String(length=12), nullable=False),
            sa.Column("mode", sa.String(length=20), nullable=False),
            sa.Column("estado", sa.String(length=20), nullable=False),
            sa.Column("active_activity_id", sa.Integer(), nullable=True),
            sa.Column("presentador_id", sa.Integer(), nullable=True),
            sa.Column("config_json", json_payload, nullable=False),
            sa.Column("opened_at", sa.DateTime(), nullable=True),
            sa.Column("closed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["presentador_id"], ["usuario.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("code"),
        )
        op.create_index(op.f("ix_live_session_code"), "live_session", ["code"], unique=True)

    if "live_activity" not in tables:
        op.create_table(
            "live_activity",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("session_id", sa.Integer(), nullable=False),
            sa.Column("template_id", sa.Integer(), nullable=True),
            sa.Column("orden", sa.Integer(), nullable=False),
            sa.Column("tipo", sa.String(length=40), nullable=False),
            sa.Column("titulo", sa.String(length=180), nullable=False),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("estado", sa.String(length=20), nullable=False),
            sa.Column("config_json", json_payload, nullable=False),
            sa.Column("payload_json", json_payload, nullable=False),
            sa.Column("opened_at", sa.DateTime(), nullable=True),
            sa.Column("closed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["session_id"], ["live_session.id"]),
            sa.ForeignKeyConstraint(["template_id"], ["live_reactivo_template.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("session_id", "orden", name="uq_live_activity_session_order"),
        )
        op.create_index(op.f("ix_live_activity_tipo"), "live_activity", ["tipo"], unique=False)

    if "live_participant" not in tables:
        op.create_table(
            "live_participant",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("session_id", sa.Integer(), nullable=False),
            sa.Column("token", sa.String(length=120), nullable=False),
            sa.Column("ultima_actividad_at", sa.DateTime(), nullable=False),
            sa.Column("connected", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["session_id"], ["live_session.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("session_id", "token", name="uq_live_participant_session_token"),
        )

    if "live_response" not in tables:
        op.create_table(
            "live_response",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("session_id", sa.Integer(), nullable=False),
            sa.Column("activity_id", sa.Integer(), nullable=False),
            sa.Column("participant_id", sa.Integer(), nullable=False),
            sa.Column("response_key", sa.String(length=80), nullable=False),
            sa.Column("payload_json", json_payload, nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["activity_id"], ["live_activity.id"]),
            sa.ForeignKeyConstraint(["participant_id"], ["live_participant.id"]),
            sa.ForeignKeyConstraint(["session_id"], ["live_session.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("activity_id", "participant_id", "response_key", name="uq_live_response_activity_participant_key"),
        )


def downgrade():
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "live_response" in tables:
        op.drop_table("live_response")
    if "live_participant" in tables:
        op.drop_table("live_participant")
    if "live_activity" in tables:
        op.drop_index(op.f("ix_live_activity_tipo"), table_name="live_activity")
        op.drop_table("live_activity")
    if "live_session" in tables:
        op.drop_index(op.f("ix_live_session_code"), table_name="live_session")
        op.drop_table("live_session")
    if "live_reactivo_template" in tables:
        op.drop_index(op.f("ix_live_reactivo_template_tipo"), table_name="live_reactivo_template")
        op.drop_table("live_reactivo_template")
    if "usuario" in tables:
        usuario_columns = {column["name"] for column in inspector.get_columns("usuario")}
        if "acceso_live" in usuario_columns:
            op.drop_column("usuario", "acceso_live")
