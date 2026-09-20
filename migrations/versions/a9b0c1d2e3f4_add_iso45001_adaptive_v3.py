"""add ISO 45001 adaptive capture v3

Revision ID: a9b0c1d2e3f4
Revises: f7a8b9c0d1e2
Create Date: 2026-07-19 13:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "a9b0c1d2e3f4"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


VERSION_TABLE = "iso45001_cuestionario_version"
REACTIVE_TABLE = "iso45001_reactivo"
RESPONSE_TABLE = "iso45001_respuesta"
EVIDENCE_TABLE = "iso45001_evidencia"
POINT_RESPONSE_TABLE = "iso45001_evaluacion_control_evidencia_punto"
DOCUMENT_EVIDENCE_TABLE = "iso45001_evidencia_documental"

V1_SLUG = "iso45001_2018_amd1_2024_diagnostico_v1"
V2_SLUG = "iso45001_2018_amd1_2024_diagnostico_v2_cobertura_documental"
V1_CATALOG_HASH = "b338047bc425d19257d7a4c28a9f58a332b9e69af3dd48db32f69af3e784b6aa"
V2_CATALOG_HASH = "42355beeb800aa7c558531af862cb86ac389f1b212c20b93cb5e66c75cb58205"
JSON_PAYLOAD = sa.JSON().with_variant(
    postgresql.JSONB(astext_type=sa.Text()),
    "postgresql",
)


def _has_table(bind, table_name):
    return table_name in sa.inspect(bind).get_table_names()


def _column_names(bind, table_name):
    if not _has_table(bind, table_name):
        return set()
    return {column["name"] for column in sa.inspect(bind).get_columns(table_name)}


def _index_names(bind, table_name):
    if not _has_table(bind, table_name):
        return set()
    return {
        index["name"]
        for index in sa.inspect(bind).get_indexes(table_name)
        if index.get("name")
    }


def _add_columns(bind, table_name, columns):
    existing = _column_names(bind, table_name)
    missing = [column for column in columns if column.name not in existing]
    if not missing:
        return
    with op.batch_alter_table(table_name) as batch_op:
        for column in missing:
            batch_op.add_column(column)


def _drop_columns(bind, table_name, column_names):
    existing = _column_names(bind, table_name)
    targets = [column_name for column_name in column_names if column_name in existing]
    if not targets:
        return
    with op.batch_alter_table(table_name) as batch_op:
        for column_name in targets:
            batch_op.drop_column(column_name)


def upgrade():
    bind = op.get_bind()

    _add_columns(
        bind,
        VERSION_TABLE,
        [
            sa.Column(
                "capture_mode",
                sa.String(length=30),
                nullable=False,
                server_default="individual",
            ),
            sa.Column(
                "document_coverage_mode",
                sa.String(length=30),
                nullable=False,
                server_default="por_reactivo",
            ),
            sa.Column(
                "scoring_scheme",
                sa.String(length=40),
                nullable=False,
                server_default="escala_0_1_2_v1",
            ),
            sa.Column("catalog_hash", sa.String(length=64), nullable=True),
        ],
    )
    if _has_table(bind, VERSION_TABLE):
        bind.execute(
            sa.text(
                f"""
                UPDATE {VERSION_TABLE}
                SET document_coverage_mode = 'por_control',
                    catalog_hash = :catalog_hash
                WHERE slug = :slug
                """
            ),
            {"catalog_hash": V2_CATALOG_HASH, "slug": V2_SLUG},
        )
        bind.execute(
            sa.text(
                f"""
                UPDATE {VERSION_TABLE}
                SET catalog_hash = :catalog_hash
                WHERE slug = :slug
                """
            ),
            {"catalog_hash": V1_CATALOG_HASH, "slug": V1_SLUG},
        )
        index_name = "ix_iso45001_cuestionario_version_catalog_hash"
        if index_name not in _index_names(bind, VERSION_TABLE):
            op.create_index(index_name, VERSION_TABLE, ["catalog_hash"], unique=False)

    _add_columns(
        bind,
        REACTIVE_TABLE,
        [sa.Column("variable_principal", sa.String(length=120), nullable=True)],
    )
    _add_columns(
        bind,
        RESPONSE_TABLE,
        [
            sa.Column(
                "origen_captura",
                sa.String(length=20),
                nullable=False,
                server_default="individual",
            ),
            sa.Column("lote_captura", sa.String(length=36), nullable=True),
        ],
    )
    _add_columns(
        bind,
        EVIDENCE_TABLE,
        [sa.Column("sha256", sa.String(length=64), nullable=True)],
    )
    _add_columns(
        bind,
        POINT_RESPONSE_TABLE,
        [
            sa.Column(
                "evaluado",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column(
                "origen_captura",
                sa.String(length=20),
                nullable=False,
                server_default="individual",
            ),
            sa.Column("lote_captura", sa.String(length=36), nullable=True),
        ],
    )
    _add_columns(
        bind,
        DOCUMENT_EVIDENCE_TABLE,
        [sa.Column("sha256", sa.String(length=64), nullable=True)],
    )

    if not _has_table(bind, "iso45001_control_evidencia_punto_reactivo"):
        op.create_table(
            "iso45001_control_evidencia_punto_reactivo",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("control_evidencia_punto_id", sa.Integer(), nullable=False),
            sa.Column("reactivo_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(
                ["control_evidencia_punto_id"],
                ["iso45001_control_evidencia_punto.id"],
            ),
            sa.ForeignKeyConstraint(["reactivo_id"], ["iso45001_reactivo.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "control_evidencia_punto_id",
                "reactivo_id",
                name="uq_iso45001_control_punto_reactivo",
            ),
        )

    if not _has_table(bind, "iso45001_reactivo_crosswalk"):
        op.create_table(
            "iso45001_reactivo_crosswalk",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("version_origen_id", sa.Integer(), nullable=False),
            sa.Column("reactivo_origen_id", sa.Integer(), nullable=False),
            sa.Column("version_destino_id", sa.Integer(), nullable=False),
            sa.Column("reactivo_destino_id", sa.Integer(), nullable=False),
            sa.Column("tipo", sa.String(length=20), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(
                ["version_origen_id"],
                ["iso45001_cuestionario_version.id"],
            ),
            sa.ForeignKeyConstraint(
                ["reactivo_origen_id"],
                ["iso45001_reactivo.id"],
            ),
            sa.ForeignKeyConstraint(
                ["version_destino_id"],
                ["iso45001_cuestionario_version.id"],
            ),
            sa.ForeignKeyConstraint(
                ["reactivo_destino_id"],
                ["iso45001_reactivo.id"],
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "version_origen_id",
                "version_destino_id",
                "reactivo_origen_id",
                name="uq_iso45001_crosswalk_origen",
            ),
            sa.UniqueConstraint(
                "version_origen_id",
                "version_destino_id",
                "reactivo_destino_id",
                name="uq_iso45001_crosswalk_destino",
            ),
            sa.UniqueConstraint(
                "reactivo_origen_id",
                "reactivo_destino_id",
                name="uq_iso45001_crosswalk_par",
            ),
        )

    if not _has_table(bind, "iso45001_evidencia_documental_punto"):
        op.create_table(
            "iso45001_evidencia_documental_punto",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("evidencia_documental_id", sa.Integer(), nullable=False),
            sa.Column(
                "evaluacion_control_evidencia_punto_id",
                sa.Integer(),
                nullable=False,
            ),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(
                ["evidencia_documental_id"],
                ["iso45001_evidencia_documental.id"],
            ),
            sa.ForeignKeyConstraint(
                ["evaluacion_control_evidencia_punto_id"],
                ["iso45001_evaluacion_control_evidencia_punto.id"],
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "evidencia_documental_id",
                "evaluacion_control_evidencia_punto_id",
                name="uq_iso45001_evidencia_documental_punto",
            ),
        )

    if not _has_table(bind, "iso45001_cambio_captura"):
        op.create_table(
            "iso45001_cambio_captura",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("evaluacion_id", sa.Integer(), nullable=False),
            sa.Column("entidad_tipo", sa.String(length=30), nullable=False),
            sa.Column("entidad_id", sa.Integer(), nullable=True),
            sa.Column("reactivo_id", sa.Integer(), nullable=True),
            sa.Column("punto_id", sa.Integer(), nullable=True),
            sa.Column("valor_anterior", JSON_PAYLOAD, nullable=True),
            sa.Column("valor_nuevo", JSON_PAYLOAD, nullable=True),
            sa.Column("origen", sa.String(length=20), nullable=False),
            sa.Column("lote_id", sa.String(length=36), nullable=True),
            sa.Column("usuario_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["evaluacion_id"], ["iso45001_evaluacion.id"]),
            sa.ForeignKeyConstraint(["reactivo_id"], ["iso45001_reactivo.id"]),
            sa.ForeignKeyConstraint(
                ["punto_id"],
                ["iso45001_evaluacion_control_evidencia_punto.id"],
            ),
            sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_iso45001_cambio_evaluacion_fecha",
            "iso45001_cambio_captura",
            ["evaluacion_id", "created_at"],
            unique=False,
        )
        op.create_index(
            "ix_iso45001_cambio_lote",
            "iso45001_cambio_captura",
            ["lote_id"],
            unique=False,
        )

    if not _has_table(bind, "iso45001_evaluacion_snapshot_cierre"):
        op.create_table(
            "iso45001_evaluacion_snapshot_cierre",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("evaluacion_id", sa.Integer(), nullable=False),
            sa.Column("version_id", sa.Integer(), nullable=False),
            sa.Column("usuario_id", sa.Integer(), nullable=False),
            sa.Column("catalog_slug", sa.String(length=80), nullable=False),
            sa.Column("catalog_hash", sa.String(length=64), nullable=False),
            sa.Column("scoring_scheme", sa.String(length=40), nullable=False),
            sa.Column("contenido", JSON_PAYLOAD, nullable=False),
            sa.Column("contenido_sha256", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["evaluacion_id"], ["iso45001_evaluacion.id"]),
            sa.ForeignKeyConstraint(
                ["version_id"],
                ["iso45001_cuestionario_version.id"],
            ),
            sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("evaluacion_id"),
        )


def downgrade():
    bind = op.get_bind()

    for table_name in (
        "iso45001_evaluacion_snapshot_cierre",
        "iso45001_cambio_captura",
        "iso45001_evidencia_documental_punto",
        "iso45001_reactivo_crosswalk",
        "iso45001_control_evidencia_punto_reactivo",
    ):
        if _has_table(bind, table_name):
            op.drop_table(table_name)

    _drop_columns(bind, DOCUMENT_EVIDENCE_TABLE, ["sha256"])
    _drop_columns(
        bind,
        POINT_RESPONSE_TABLE,
        ["lote_captura", "origen_captura", "evaluado"],
    )
    _drop_columns(bind, EVIDENCE_TABLE, ["sha256"])
    _drop_columns(bind, RESPONSE_TABLE, ["lote_captura", "origen_captura"])
    _drop_columns(bind, REACTIVE_TABLE, ["variable_principal"])

    version_hash_index = "ix_iso45001_cuestionario_version_catalog_hash"
    if version_hash_index in _index_names(bind, VERSION_TABLE):
        op.drop_index(version_hash_index, table_name=VERSION_TABLE)
    _drop_columns(
        bind,
        VERSION_TABLE,
        ["catalog_hash", "scoring_scheme", "document_coverage_mode", "capture_mode"],
    )
