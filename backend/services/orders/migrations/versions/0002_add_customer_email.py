import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("customer_email", sa.String(length=320), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "customer_email")
