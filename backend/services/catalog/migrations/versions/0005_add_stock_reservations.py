import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

STATUSES = ("RESERVED", "FAILED", "RELEASED")


def upgrade() -> None:
    op.create_table(
        "stock_reservations",
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("failure_reason", sa.String(length=30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN (" + ", ".join(f"'{item}'" for item in STATUSES) + ")",
            name="ck_stock_reservations_status_known",
        ),
        sa.PrimaryKeyConstraint("order_id", name="pk_stock_reservations"),
    )
    op.create_table(
        "stock_reservation_lines",
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_stock_reservation_lines_quantity_positive"),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["stock_reservations.order_id"],
            name="fk_stock_reservation_lines_order_id_stock_reservations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("order_id", "sku", name="pk_stock_reservation_lines"),
    )


def downgrade() -> None:
    op.drop_table("stock_reservation_lines")
    op.drop_table("stock_reservations")
