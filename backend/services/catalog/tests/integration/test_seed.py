from collections.abc import Callable

import pytest
from sqlalchemy import text

from catalog.infra.database import create_engine
from catalog.tools.seed import seed_products

pytestmark = pytest.mark.integration


async def scalar(url: str, query: str) -> object:
    engine = create_engine(url)
    try:
        async with engine.connect() as connection:
            return await connection.scalar(text(query))
    finally:
        await engine.dispose()


async def seed(url: str, count: int, chunk_size: int = 400) -> int:
    engine = create_engine(url)
    try:
        return await seed_products(engine, count, chunk_size)
    finally:
        await engine.dispose()


async def test_seeding_twice_is_safe_and_the_second_run_adds_nothing(
    empty_database_url: str, alembic_runner: Callable[[str, str, str], None]
) -> None:
    alembic_runner(empty_database_url, "upgrade", "head")

    first = await seed(empty_database_url, 1000)
    second = await seed(empty_database_url, 1000)

    assert (first, second) == (1000, 0)
    assert await scalar(empty_database_url, "SELECT count(*) FROM products") == 1000


async def test_asking_for_more_only_adds_the_missing_products(
    empty_database_url: str, alembic_runner: Callable[[str, str, str], None]
) -> None:
    alembic_runner(empty_database_url, "upgrade", "head")
    await seed(empty_database_url, 700)

    added = await seed(empty_database_url, 1000)

    assert added == 300
    assert await scalar(empty_database_url, "SELECT count(*) FROM products") == 1000


async def test_seeding_never_touches_products_created_by_hand(
    empty_database_url: str, alembic_runner: Callable[[str, str, str], None]
) -> None:
    alembic_runner(empty_database_url, "upgrade", "head")
    engine = create_engine(empty_database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO products (sku, name, price, stock) "
                    "VALUES ('SEED-0000001', 'Hand made', 1.00, 1)"
                )
            )
    finally:
        await engine.dispose()

    added = await seed(empty_database_url, 10)

    assert added == 9
    name = await scalar(empty_database_url, "SELECT name FROM products WHERE sku = 'SEED-0000001'")
    assert name == "Hand made"


async def test_seed_data_exercises_ties_stock_categories_and_soft_deletes(
    empty_database_url: str, alembic_runner: Callable[[str, str, str], None]
) -> None:
    alembic_runner(empty_database_url, "upgrade", "head")
    await seed(empty_database_url, 5000)

    async def count(condition: str) -> int:
        value = await scalar(empty_database_url, f"SELECT count(*) FROM products WHERE {condition}")
        return int(str(value))

    assert await count("deleted_at IS NOT NULL") == 50
    assert await count("stock = 0") == 1000
    assert await count("category_id IS NULL") > 0
    assert await count("category_id IS NOT NULL") > 4000
    duplicate_prices = await scalar(
        empty_database_url,
        "SELECT count(*) FROM (SELECT price FROM products GROUP BY price HAVING count(*) > 1) d",
    )
    duplicate_moments = await scalar(
        empty_database_url,
        "SELECT count(*) FROM (SELECT created_at FROM products GROUP BY created_at "
        "HAVING count(*) > 1) d",
    )
    assert int(str(duplicate_prices)) > 100
    assert int(str(duplicate_moments)) > 100


async def test_seeded_products_are_searchable_right_away(
    empty_database_url: str, alembic_runner: Callable[[str, str, str], None]
) -> None:
    alembic_runner(empty_database_url, "upgrade", "head")
    await seed(empty_database_url, 2000)

    found = await scalar(
        empty_database_url,
        "SELECT count(*) FROM products "
        "WHERE search_vector @@ websearch_to_tsquery('english'::regconfig, 'running shoes')",
    )

    assert int(str(found)) > 50
