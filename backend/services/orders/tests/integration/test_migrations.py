from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from orders.infra.database import create_engine, database_readiness_check
from orders.infra.models import Base

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
TABLES = {
    "alembic_version",
    "orders",
    "order_lines",
    "order_status_history",
    "idempotency_keys",
    "outbox",
}

INSERT_ORDER = (
    "INSERT INTO orders (id, customer_id, status, total, currency, card_last4, shipping_address,"
    " correlation_id, created_at, updated_at) VALUES (:id, :customer, :status, :total, 'USD',"
    " :card, '{}', :correlation, now(), now())"
)


async def fetch_all(url: str, query: str) -> list[tuple[object, ...]]:
    engine = create_engine(url)
    try:
        async with engine.connect() as connection:
            return [tuple(row) for row in await connection.execute(text(query))]
    finally:
        await engine.dispose()


async def execute(url: str, query: str, **params: object) -> None:
    engine = create_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text(query), params)
    finally:
        await engine.dispose()


async def insert_order(
    url: str, status: str = "PENDING", total: str = "10.00", card: str = "1111"
) -> None:
    await execute(
        url,
        INSERT_ORDER,
        id=uuid4(),
        customer=uuid4(),
        status=status,
        total=total,
        card=card,
        correlation=uuid4(),
    )


async def test_models_match_the_migrated_schema(migrated_database_url: str) -> None:
    engine = create_engine(migrated_database_url)
    try:
        async with engine.connect() as connection:
            differences = await connection.run_sync(
                lambda sync: compare_metadata(MigrationContext.configure(sync), Base.metadata)
            )
    finally:
        await engine.dispose()

    assert differences == []


async def test_upgrade_creates_the_tables_and_downgrade_removes_them(
    empty_database_url: str, alembic_runner: Callable[[str, str, str], None]
) -> None:
    alembic_runner(empty_database_url, "upgrade", "head")
    query = "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"

    created = {name for (name,) in await fetch_all(empty_database_url, query)}
    alembic_runner(empty_database_url, "downgrade", "base")
    removed = await fetch_all(empty_database_url, query)
    alembic_runner(empty_database_url, "upgrade", "head")

    assert created == TABLES
    assert removed == [("alembic_version",)]


@pytest.mark.parametrize(
    ("kwargs", "constraint"),
    [
        ({"status": "SHIPPED"}, "ck_orders_status_known"),
        ({"total": "-0.01"}, "ck_orders_total_non_negative"),
        ({"card": "4929123456781111"}, "value too long"),
        ({"card": "11a1"}, "ck_orders_card_last4_digits"),
        ({"card": "111"}, "ck_orders_card_last4_digits"),
    ],
)
async def test_the_database_refuses_bad_orders_and_anything_but_four_card_digits(
    migrated_database_url: str, kwargs: dict[str, str], constraint: str
) -> None:
    with pytest.raises(Exception, match=constraint):
        await insert_order(migrated_database_url, **kwargs)


async def test_a_line_needs_a_positive_quantity_and_an_existing_order(
    migrated_database_url: str,
) -> None:
    with pytest.raises(IntegrityError, match="fk_order_lines_order_id_orders"):
        await execute(
            migrated_database_url,
            "INSERT INTO order_lines (order_id, sku, position, quantity, unit_price)"
            " VALUES (:id, 'A', 0, 1, 1.00)",
            id=uuid4(),
        )


async def test_money_is_numeric_with_two_decimals(migrated_database_url: str) -> None:
    rows = await fetch_all(
        migrated_database_url,
        "SELECT column_name, data_type, numeric_precision, numeric_scale"
        " FROM information_schema.columns WHERE table_name IN ('orders', 'order_lines')"
        " AND column_name IN ('total', 'unit_price') ORDER BY column_name",
    )

    assert rows == [("total", "numeric", 12, 2), ("unit_price", "numeric", 12, 2)]


async def test_database_readiness_check_passes_against_a_real_database(
    migrated_database_url: str,
) -> None:
    engine = create_engine(migrated_database_url)
    try:
        await database_readiness_check(engine).probe()
    finally:
        await engine.dispose()


async def test_the_email_column_is_added_nullable_and_old_orders_keep_a_null_email(
    empty_database_url: str, alembic_runner: Callable[[str, str, str], None]
) -> None:
    alembic_runner(empty_database_url, "upgrade", "0001")
    await insert_order(empty_database_url)
    columns = "SELECT column_name FROM information_schema.columns WHERE table_name = 'orders'"
    before = {name for (name,) in await fetch_all(empty_database_url, columns)}

    alembic_runner(empty_database_url, "upgrade", "head")
    after = {name for (name,) in await fetch_all(empty_database_url, columns)}
    rows = await fetch_all(empty_database_url, "SELECT customer_email FROM orders")
    shape = await fetch_all(
        empty_database_url,
        "SELECT is_nullable, character_maximum_length FROM information_schema.columns"
        " WHERE table_name = 'orders' AND column_name = 'customer_email'",
    )

    assert "customer_email" not in before
    assert after - before == {"customer_email"}
    assert rows == [(None,)]
    assert shape == [("YES", 320)]


async def test_downgrading_removes_only_the_email_column(
    empty_database_url: str, alembic_runner: Callable[[str, str, str], None]
) -> None:
    alembic_runner(empty_database_url, "upgrade", "head")
    await insert_order(empty_database_url)

    alembic_runner(empty_database_url, "downgrade", "0001")
    rows = await fetch_all(empty_database_url, "SELECT count(*) FROM orders")
    columns = await fetch_all(
        empty_database_url,
        "SELECT column_name FROM information_schema.columns"
        " WHERE table_name = 'orders' AND column_name = 'customer_email'",
    )
    alembic_runner(empty_database_url, "upgrade", "head")

    assert rows == [(1,)]
    assert columns == []
