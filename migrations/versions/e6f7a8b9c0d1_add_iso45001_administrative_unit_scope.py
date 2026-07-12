"""add ISO 45001 administrative unit scope

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-07-11 23:50:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


TABLE_NAME = "iso45001_evaluacion"
OLD_UNIQUE = "uq_iso45001_evaluacion_ciclo_dependencia"
NEW_UNIQUE = "uq_iso45001_evaluacion_ciclo_area"
AREA_FOREIGN_KEY = "fk_iso45001_evaluacion_area"


def _schema_state(bind):
    inspector = sa.inspect(bind)
    return {
        "columns": {column["name"] for column in inspector.get_columns(TABLE_NAME)},
        "uniques": {
            constraint.get("name")
            for constraint in inspector.get_unique_constraints(TABLE_NAME)
            if constraint.get("name")
        },
        "foreign_keys": {
            constraint.get("name")
            for constraint in inspector.get_foreign_keys(TABLE_NAME)
            if constraint.get("name")
        },
    }


def upgrade():
    bind = op.get_bind()
    state = _schema_state(bind)
    needs_change = (
        "area_id" not in state["columns"]
        or OLD_UNIQUE in state["uniques"]
        or NEW_UNIQUE not in state["uniques"]
        or AREA_FOREIGN_KEY not in state["foreign_keys"]
    )
    if not needs_change:
        return

    # Batch mode safely recreates this table on SQLite and emits regular ALTER
    # operations on engines that support them.  Every operation is conditional
    # so an interrupted SQLite deployment can be retried.
    with op.batch_alter_table(TABLE_NAME) as batch_op:
        if "area_id" not in state["columns"]:
            batch_op.add_column(sa.Column("area_id", sa.Integer(), nullable=True))
        if OLD_UNIQUE in state["uniques"]:
            batch_op.drop_constraint(OLD_UNIQUE, type_="unique")
        if NEW_UNIQUE not in state["uniques"]:
            batch_op.create_unique_constraint(NEW_UNIQUE, ["ciclo_id", "area_id"])
        if AREA_FOREIGN_KEY not in state["foreign_keys"]:
            batch_op.create_foreign_key(AREA_FOREIGN_KEY, "area", ["area_id"], ["id"])


def downgrade():
    bind = op.get_bind()
    duplicate_scope = bind.execute(
        sa.text(
            """
            SELECT ciclo_id, dependencia_id, COUNT(*) AS total
            FROM iso45001_evaluacion
            GROUP BY ciclo_id, dependencia_id
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicate_scope:
        raise RuntimeError(
            "No se puede revertir la asignación ISO 45001 por unidad: "
            "existen varias unidades de una dependencia dentro del mismo ciclo."
        )

    state = _schema_state(bind)
    with op.batch_alter_table(TABLE_NAME) as batch_op:
        if AREA_FOREIGN_KEY in state["foreign_keys"]:
            batch_op.drop_constraint(AREA_FOREIGN_KEY, type_="foreignkey")
        if NEW_UNIQUE in state["uniques"]:
            batch_op.drop_constraint(NEW_UNIQUE, type_="unique")
        if "area_id" in state["columns"]:
            batch_op.drop_column("area_id")
        if OLD_UNIQUE not in state["uniques"]:
            batch_op.create_unique_constraint(OLD_UNIQUE, ["ciclo_id", "dependencia_id"])
