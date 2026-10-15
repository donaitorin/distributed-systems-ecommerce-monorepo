from collections.abc import Callable

import httpx
import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from auth_testing.support import FakeHasher, auth_settings
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from auth.infra.database import create_engine, database_readiness_check
from auth.infra.keys import KeyStore
from auth.infra.models import Base
from auth.main import create_auth_app

pytestmark = pytest.mark.integration


async def fetch_all(url: str, query: str) -> list[tuple[object, ...]]:
    engine = create_engine(url)
    try:
        async with engine.connect() as connection:
            return [tuple(row) for row in await connection.execute(text(query))]
    finally:
        await engine.dispose()


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


async def test_upgrade_creates_the_tables_and_the_outbox(
    empty_database_url: str, alembic_runner: Callable[[str, str, str], None]
) -> None:
    alembic_runner(empty_database_url, "upgrade", "head")

    tables = await fetch_all(
        empty_database_url,
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'",
    )

    assert {name for (name,) in tables} == {"alembic_version", "users", "refresh_tokens", "outbox"}


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


async def test_the_database_rejects_an_unknown_role(migrated_database_url: str) -> None:
    engine = create_engine(migrated_database_url)
    try:
        async with engine.begin() as connection:
            with pytest.raises(IntegrityError, match="ck_users_role_known"):
                await connection.execute(
                    text(
                        "INSERT INTO users (email, password_hash, role) "
                        "VALUES ('x@example.com', 'hash', 'superuser')"
                    )
                )
    finally:
        await engine.dispose()


async def test_the_database_enforces_unique_emails(migrated_database_url: str) -> None:
    engine = create_engine(migrated_database_url)
    insert = text(
        "INSERT INTO users (email, password_hash, role) VALUES ('dup@example.com', 'h', 'customer')"
    )
    try:
        async with engine.begin() as connection:
            await connection.execute(insert)
        async with engine.begin() as connection:
            with pytest.raises(IntegrityError, match="uq_users_email"):
                await connection.execute(insert)
    finally:
        await engine.dispose()


async def test_database_readiness_check_passes_against_a_real_database(
    migrated_database_url: str,
) -> None:
    engine = create_engine(migrated_database_url)
    try:
        await database_readiness_check(engine).probe()
    finally:
        await engine.dispose()


async def test_ready_endpoint_is_green_with_a_reachable_database(
    migrated_database_url: str, key_store: KeyStore
) -> None:
    engine = create_engine(migrated_database_url)
    app = create_auth_app(auth_settings(), engine, keys=key_store, hasher=FakeHasher())
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/ready")
    finally:
        await engine.dispose()

    assert response.status_code == 200
    assert response.json()["checks"] == {"database": "ok"}
