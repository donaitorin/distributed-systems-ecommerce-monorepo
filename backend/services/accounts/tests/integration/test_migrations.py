from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from accounts.infra.database import create_engine, database_readiness_check
from accounts.infra.models import Base

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


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


INSERT_PROFILE = (
    "INSERT INTO profiles (user_id, email, role, role_updated_at) "
    "VALUES (:id, :email, 'customer', now())"
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


async def test_upgrade_creates_the_tables(
    empty_database_url: str, alembic_runner: Callable[[str, str, str], None]
) -> None:
    alembic_runner(empty_database_url, "upgrade", "head")

    tables = await fetch_all(
        empty_database_url,
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'",
    )

    assert {name for (name,) in tables} == {"alembic_version", "profiles", "addresses"}


async def test_downgrade_removes_everything_and_upgrade_can_run_again(
    empty_database_url: str, alembic_runner: Callable[[str, str, str], None]
) -> None:
    alembic_runner(empty_database_url, "upgrade", "head")
    alembic_runner(empty_database_url, "downgrade", "base")

    tables = await fetch_all(
        empty_database_url,
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'",
    )
    assert tables == [("alembic_version",)]

    alembic_runner(empty_database_url, "upgrade", "head")


async def test_the_database_rejects_an_email_with_uppercase_letters(
    migrated_database_url: str,
) -> None:
    with pytest.raises(IntegrityError, match="ck_profiles_email_lowercase"):
        await execute(migrated_database_url, INSERT_PROFILE, id=uuid4(), email="Ada@Example.com")


async def test_the_database_rejects_a_malformed_country(migrated_database_url: str) -> None:
    user_id = uuid4()
    await execute(migrated_database_url, INSERT_PROFILE, id=user_id, email="c@example.com")

    with pytest.raises(IntegrityError, match="ck_addresses_country_alpha2"):
        await execute(
            migrated_database_url,
            "INSERT INTO addresses (user_id, recipient_name, line1, city, postal_code, country) "
            "VALUES (:id, 'Ada', '1 St', 'Madrid', '28001', 'es')",
            id=user_id,
        )


async def test_an_address_needs_an_existing_profile(migrated_database_url: str) -> None:
    with pytest.raises(IntegrityError, match="fk_addresses_user_id_profiles"):
        await execute(
            migrated_database_url,
            "INSERT INTO addresses (user_id, recipient_name, line1, city, postal_code, country) "
            "VALUES (:id, 'Ada', '1 St', 'Madrid', '28001', 'ES')",
            id=uuid4(),
        )


async def test_deleting_a_profile_deletes_its_addresses(migrated_database_url: str) -> None:
    user_id = uuid4()
    await execute(migrated_database_url, INSERT_PROFILE, id=user_id, email="d@example.com")
    await execute(
        migrated_database_url,
        "INSERT INTO addresses (user_id, recipient_name, line1, city, postal_code, country) "
        "VALUES (:id, 'Ada', '1 St', 'Madrid', '28001', 'ES')",
        id=user_id,
    )

    await execute(migrated_database_url, "DELETE FROM profiles WHERE user_id = :id", id=user_id)

    remaining = await fetch_all(
        migrated_database_url, f"SELECT 1 FROM addresses WHERE user_id = '{user_id}'"
    )
    assert remaining == []


async def test_database_readiness_check_passes_against_a_real_database(
    migrated_database_url: str,
) -> None:
    engine = create_engine(migrated_database_url)
    try:
        await database_readiness_check(engine).probe()
    finally:
        await engine.dispose()
