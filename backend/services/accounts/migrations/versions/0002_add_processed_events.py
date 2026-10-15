import sqlalchemy as sa
from alembic import op

from accounts.infra.models import NAMING_CONVENTION
from ecommerce_messaging import processed_events_table

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)
    processed_events_table(metadata)
    metadata.create_all(op.get_bind())


def downgrade() -> None:
    op.drop_table("processed_events")
