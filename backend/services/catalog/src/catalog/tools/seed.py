import argparse
import asyncio
import os
import sys
from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from catalog.infra.database import create_engine
from catalog.settings import CatalogSettings

DEFAULT_COUNT = 200_000
MAX_COUNT = 5_000_000
CHUNK_SIZE = 50_000

INSERT_SEED_PRODUCTS = text(
    """
    INSERT INTO products
        (id, sku, name, description, category_id, price, stock, weight_kg,
         version, created_at, updated_at, deleted_at)
    SELECT
        gen_random_uuid(),
        'SEED-' || lpad(n::text, 7, '0'),
        brand || ' ' || adjective || ' ' || noun || ' M' || model,
        brand || ' ' || adjective || ' ' || noun || ' with ' || feature || ' for everyday use',
        (SELECT array_agg(id ORDER BY slug) FROM categories)[1 + n % 19],
        ((n * 7919) % 1200 + 1)::numeric * 79 / 100,
        CASE WHEN n % 5 = 0 THEN 0 ELSE (n * 31) % 500 + 1 END,
        CASE WHEN n % 7 = 0 THEN NULL ELSE ((n * 13) % 5000)::numeric / 1000 END,
        1,
        created,
        created,
        CASE WHEN n % 100 = 0 THEN created END
    FROM (
        SELECT
            n,
            (ARRAY['Nordwind', 'Alpenglow', 'Kestrel', 'Marlow', 'Tidewater', 'Fernhill',
                   'Oakridge', 'Solace', 'Quillon', 'Brightwater', 'Harlow', 'Ironwood',
                   'Juniper', 'Larkspur', 'Meridian', 'Northfield', 'Obsidian', 'Pinecrest',
                   'Redwood', 'Silverleaf', 'Thornbury', 'Umber', 'Valence', 'Willowbrook',
                   'Yarrow', 'Zephyr', 'Ashford', 'Birchwood', 'Cobalt', 'Driftwood',
                   'Emberly', 'Foxglove', 'Glenmoor', 'Hollis', 'Indigo', 'Jasper',
                   'Kingfisher', 'Lumen', 'Maplewood', 'Nimbus'])[1 + (n * 17) % 40] AS brand,
            (n * 7) % 9973 AS model,
            (ARRAY['Trail', 'Classic', 'Lightweight', 'Premium', 'Compact', 'Waterproof',
                   'Ergonomic', 'Vintage', 'Eco', 'Pro', 'Urban', 'Essential'])[1 + n % 12]
                AS adjective,
            (ARRAY['Running Shoes', 'Backpack', 'Water Bottle', 'Desk Lamp', 'Notebook',
                   'Headphones', 'Coffee Mug', 'Yoga Mat', 'Wireless Mouse', 'Rain Jacket',
                   'Cutting Board', 'Garden Gloves', 'Travel Pillow', 'Phone Stand',
                   'Dog Leash', 'Board Game'])[1 + (n / 12) % 16] AS noun,
            (ARRAY['a durable finish', 'soft padding', 'a modern design', 'extra grip',
                   'recycled materials', 'a two year warranty'])[1 + (n / 7) % 6] AS feature,
            TIMESTAMPTZ '2025-01-01 00:00:00+00'
                + ((n * 37) % 2000) * INTERVAL '2 hours' AS created
        FROM generate_series(CAST(:first AS integer), CAST(:last AS integer)) AS n
    ) AS generated
    ON CONFLICT (sku) DO NOTHING
    """
)


async def seed_products(engine: AsyncEngine, count: int, chunk_size: int = CHUNK_SIZE) -> int:
    inserted = 0
    for first in range(1, count + 1, chunk_size):
        last = min(first + chunk_size - 1, count)
        async with engine.begin() as connection:
            result = await connection.execute(INSERT_SEED_PRODUCTS, {"first": first, "last": last})
            inserted += result.rowcount
    async with engine.connect() as connection:
        autocommit = await connection.execution_options(isolation_level="AUTOCOMMIT")
        await autocommit.execute(text("ANALYZE products"))
    return inserted


def parse_count(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description="Load synthetic products into the catalog")
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
    count: int = parser.parse_args(argv).count
    if not 1 <= count <= MAX_COUNT:
        parser.error(f"--count must be between 1 and {MAX_COUNT}")
    return count


async def run(count: int) -> None:
    engine = create_engine(CatalogSettings.from_env(os.environ).database_url)
    try:
        inserted = await seed_products(engine, count)
    finally:
        await engine.dispose()
    sys.stdout.write(f"requested {count} seed products, inserted {inserted}\n")


def main(argv: Sequence[str] | None = None) -> None:
    asyncio.run(run(parse_count(sys.argv[1:] if argv is None else argv)))


if __name__ == "__main__":
    main()
