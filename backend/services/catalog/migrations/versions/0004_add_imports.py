import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from catalog.infra.models import NAMING_CONVENTION
from ecommerce_messaging import outbox_table, processed_events_table

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

STATUSES = (
    "uploaded",
    "validating",
    "rejected",
    "validated",
    "queued",
    "processing",
    "completed",
    "failed",
)


def upgrade() -> None:
    op.create_table(
        "imports",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("report", postgresql.JSONB(), nullable=True),
        sa.Column("category_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("processed_rows", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_rows", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("updated_rows", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("restored_rows", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("unchanged_rows", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN (" + ", ".join(f"'{item}'" for item in STATUSES) + ")",
            name="ck_imports_status_known",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_imports"),
    )
    op.create_index(
        "uq_imports_sha256_unless_failed",
        "imports",
        ["sha256"],
        unique=True,
        postgresql_where=sa.text("status <> 'failed'"),
    )
    op.create_index("ix_imports_created_at", "imports", ["created_at"])
    op.create_table(
        "import_problems",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("import_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("severity", sa.String(length=7), nullable=False),
        sa.Column("row", sa.Integer(), nullable=True),
        sa.Column("column_name", sa.String(length=100), nullable=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["import_id"],
            ["imports.id"],
            name="fk_import_problems_import_id_imports",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_import_problems"),
    )
    op.create_index("ix_import_problems_import_id_id", "import_problems", ["import_id", "id"])
    metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)
    outbox_table(metadata)
    processed_events_table(metadata)
    metadata.create_all(op.get_bind())


def downgrade() -> None:
    op.drop_table("processed_events")
    op.drop_table("outbox")
    op.drop_index("ix_import_problems_import_id_id", table_name="import_problems")
    op.drop_table("import_problems")
    op.drop_index("ix_imports_created_at", table_name="imports")
    op.drop_index("uq_imports_sha256_unless_failed", table_name="imports")
    op.drop_table("imports")
