from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

SEARCH_VECTOR = (
    "setweight(to_tsvector('english'::regconfig, coalesce(name, '')), 'A') || "
    "setweight(to_tsvector('simple'::regconfig, sku), 'A') || "
    "setweight(to_tsvector('english'::regconfig, coalesce(description, '')), 'C')"
)
ACTIVE = "deleted_at IS NULL"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        f"ALTER TABLE products ADD COLUMN search_vector tsvector "
        f"GENERATED ALWAYS AS ({SEARCH_VECTOR}) STORED"
    )
    op.execute(
        f"CREATE INDEX ix_products_search_vector ON products USING gin (search_vector) "
        f"WHERE {ACTIVE}"
    )
    op.execute(
        f"CREATE INDEX ix_products_name_trgm ON products USING gin (name gin_trgm_ops) "
        f"WHERE {ACTIVE}"
    )
    op.execute(
        f"CREATE INDEX ix_products_created_at_id ON products (created_at, id) WHERE {ACTIVE}"
    )
    op.execute(f"CREATE INDEX ix_products_price_id ON products (price, id) WHERE {ACTIVE}")


def downgrade() -> None:
    op.execute("DROP INDEX ix_products_price_id")
    op.execute("DROP INDEX ix_products_created_at_id")
    op.execute("DROP INDEX ix_products_name_trgm")
    op.execute("DROP INDEX ix_products_search_vector")
    op.execute("ALTER TABLE products DROP COLUMN search_vector")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
