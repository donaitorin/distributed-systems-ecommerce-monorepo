import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from ecommerce_messaging import outbox_table
from orders.infra.models import NAMING_CONVENTION

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

STATUSES = ("PENDING", "STOCK_RESERVED", "PAID", "CONFIRMED", "CANCELLED")
STATUS_LIST = ", ".join(f"'{item}'" for item in STATUSES)


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("card_last4", sa.String(length=4), nullable=False),
        sa.Column("shipping_address", postgresql.JSONB(), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cancel_reason", sa.String(length=100), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"status IN ({STATUS_LIST})", name="ck_orders_status_known"),
        sa.CheckConstraint("total >= 0", name="ck_orders_total_non_negative"),
        sa.CheckConstraint("card_last4 ~ '^[0-9]{4}$'", name="ck_orders_card_last4_digits"),
        sa.PrimaryKeyConstraint("id", name="pk_orders"),
    )
    op.create_index(
        "ix_orders_customer_id_created_at_id",
        "orders",
        ["customer_id", sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_orders_created_at_id", "orders", [sa.text("created_at DESC"), sa.text("id DESC")]
    )
    op.create_index(
        "ix_orders_status_created_at_id",
        "orders",
        ["status", sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_orders_open_created_at",
        "orders",
        ["created_at"],
        postgresql_where=sa.text("status IN ('PENDING', 'STOCK_RESERVED')"),
    )
    op.create_table(
        "order_lines",
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_order_lines_quantity_positive"),
        sa.CheckConstraint("unit_price >= 0", name="ck_order_lines_unit_price_non_negative"),
        sa.ForeignKeyConstraint(
            ["order_id"], ["orders.id"], name="fk_order_lines_order_id_orders", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("order_id", "sku", name="pk_order_lines"),
    )
    op.create_table(
        "order_status_history",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"to_status IN ({STATUS_LIST})", name="ck_order_status_history_to_status_known"
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name="fk_order_status_history_order_id_orders",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_order_status_history"),
    )
    op.create_index(
        "ix_order_status_history_order_id_id", "order_status_history", ["order_id", "id"]
    )
    op.create_table(
        "idempotency_keys",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("response_status", sa.SmallInteger(), nullable=False),
        sa.Column("response_body", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "key", name="pk_idempotency_keys"),
    )
    op.create_index("ix_idempotency_keys_expires_at", "idempotency_keys", ["expires_at"])
    metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)
    outbox_table(metadata)
    metadata.create_all(op.get_bind())


def downgrade() -> None:
    op.drop_table("outbox")
    op.drop_table("idempotency_keys")
    op.drop_table("order_status_history")
    op.drop_table("order_lines")
    op.drop_table("orders")
