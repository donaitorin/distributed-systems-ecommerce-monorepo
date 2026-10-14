import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

CATEGORIES = [
    ("Accessories", "accessories"),
    ("Beauty", "beauty"),
    ("Books", "books"),
    ("Clothing", "clothing"),
    ("Electronics", "electronics"),
    ("Food & Beverage", "food-beverage"),
    ("Footwear", "footwear"),
    ("Games", "games"),
    ("Gifts", "gifts"),
    ("Health", "health"),
    ("Home & Office", "home-office"),
    ("Kitchen", "kitchen"),
    ("Misc", "misc"),
    ("Outdoors", "outdoors"),
    ("Pets", "pets"),
    ("Sports", "sports"),
    ("Stationery", "stationery"),
    ("Tools", "tools"),
]

categories = sa.table("categories", sa.column("name", sa.String), sa.column("slug", sa.String))


def upgrade() -> None:
    op.bulk_insert(categories, [{"name": name, "slug": slug} for name, slug in CATEGORIES])


def downgrade() -> None:
    slugs = [slug for _, slug in CATEGORIES]
    op.execute(categories.delete().where(categories.c.slug.in_(slugs)))
