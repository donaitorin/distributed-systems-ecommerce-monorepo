from collections.abc import Callable
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from payments.infra.database import create_engine, database_readiness_check
from payments.infra.models import Base

pytestmark = pytest.mark.integration

INSERT = (
    "INSERT INTO payments (order_id, customer_id, amount, currency, card_last4, status,"
    " correlation_id, created_at, updated_at) VALUES (:order, :customer, :amount, 'USD', :card,"
    " :status, :correlation, now(), now())"
)


async def execute(url: str, query: str, **params: object) -> None:
    engine = create_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text(query), params)
    finally:
        await engine.dispose()


async def insert(
    url: str,
    order: object | None = None,
    amount: str = "10.00",
    card: str = "1111",
    status: str = "PENDING",
) -> None:
    await execute(
        url,
        INSERT,
        order=order or uuid4(),
        customer=uuid4(),
        amount=amount,
        card=card,
        status=status,
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
    query = "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"

    async def tables() -> set[str]:
        engine = create_engine(empty_database_url)
        try:
            async with engine.connect() as connection:
                return {name for (name,) in await connection.execute(text(query))}
        finally:
            await engine.dispose()

    alembic_runner(empty_database_url, "upgrade", "head")
    created = await tables()
    alembic_runner(empty_database_url, "downgrade", "base")
    removed = await tables()
    alembic_runner(empty_database_url, "upgrade", "head")

    assert created == {"alembic_version", "payments", "outbox"}
    assert removed == {"alembic_version"}


async def test_there_is_one_payment_per_order(migrated_database_url: str) -> None:
    order = uuid4()
    await insert(migrated_database_url, order)

    with pytest.raises(IntegrityError, match="uq_payments_order_id"):
        await insert(migrated_database_url, order)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"amount": "0.00"}, "ck_payments_amount_positive"),
        ({"amount": "-1.00"}, "ck_payments_amount_positive"),
        ({"status": "SETTLED"}, "ck_payments_status_known"),
        ({"card": "11a1"}, "ck_payments_card_last4_digits"),
        ({"card": "4929123456781111"}, "value too long"),
    ],
)
async def test_the_database_refuses_bad_payments_and_anything_but_four_card_digits(
    migrated_database_url: str, kwargs: dict[str, str], message: str
) -> None:
    with pytest.raises(Exception, match=message):
        await insert(migrated_database_url, **kwargs)


async def test_database_readiness_check_passes_against_a_real_database(
    migrated_database_url: str,
) -> None:
    engine = create_engine(migrated_database_url)
    try:
        await database_readiness_check(engine).probe()
    finally:
        await engine.dispose()
