import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from ecommerce_messaging import outbox_table
from payments.infra.models import NAMING_CONVENTION

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

STATUSES = ("PENDING", "SUCCEEDED", "FAILED", "REFUNDED")
STATUS_LIST = ", ".join(f"'{item}'" for item in STATUSES)


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("card_last4", sa.String(length=4), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("failure_reason", sa.String(length=100), nullable=True),
        sa.Column("order_cancelled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("check_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"status IN ({STATUS_LIST})", name="ck_payments_status_known"),
        sa.CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        sa.CheckConstraint("card_last4 ~ '^[0-9]{4}$'", name="ck_payments_card_last4_digits"),
        sa.PrimaryKeyConstraint("id", name="pk_payments"),
        sa.UniqueConstraint("order_id", name="uq_payments_order_id"),
    )
    op.create_index(
        "ix_payments_check_after",
        "payments",
        ["check_after"],
        postgresql_where=sa.text("status = 'PENDING' AND check_after IS NOT NULL"),
    )
    op.create_index(
        "ix_payments_refund_due",
        "payments",
        ["order_id"],
        postgresql_where=sa.text("status = 'SUCCEEDED' AND order_cancelled"),
    )
    metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)
    outbox_table(metadata)
    metadata.create_all(op.get_bind())


def downgrade() -> None:
    op.drop_table("outbox")
    op.drop_table("payments")
