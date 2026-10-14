import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from catalog_testing.support import (
    SteppingClock,
    bearer,
    http_client,
    in_memory_app,
    seeded_store,
)
from fastapi import FastAPI
from sqlalchemy import make_url
from testcontainers.community.postgres import PostgresContainer

from catalog.infra.memory import InMemoryStore
from ecommerce_auth import Role
from ecommerce_auth.testing import StubTokenIssuer

CATALOG_DIR = Path(__file__).resolve().parents[1]
POSTGRES_IMAGE = "postgres:17.11-alpine"


type AlembicRunner = Callable[[str, str, str], None]


def run_alembic(database_url: str, action: str, revision: str) -> None:
    config = Config(str(CATALOG_DIR / "alembic.ini"))
    config.attributes["database_url"] = database_url
    config.attributes["configure_logging"] = False
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(getattr(command, action), config, revision).result()


class PostgresServer:
    def __init__(self, container: PostgresContainer) -> None:
        self._container = container

    def create_database(self) -> str:
        name = f"catalog_{uuid.uuid4().hex[:12]}"
        self._container.exec(
            [
                "psql",
                "--username",
                self._container.username,
                "--dbname",
                self._container.dbname,
                "-c",
                f"CREATE DATABASE {name}",
            ]
        )
        base = self._container.get_connection_url(driver="asyncpg")
        return base.rsplit("/", 1)[0] + f"/{name}"

    def create_login_role(self, database_url: str, role: str, password: str) -> None:
        database = make_url(database_url).database or ""
        escaped = password.replace("'", "''")
        for statement in (
            f"CREATE ROLE {role} LOGIN PASSWORD '{escaped}'",
            f"GRANT ALL ON DATABASE {database} TO {role}",
            f"GRANT ALL ON SCHEMA public TO {role}",
        ):
            self._container.exec(
                [
                    "psql",
                    "--username",
                    self._container.username,
                    "--dbname",
                    database if "SCHEMA" in statement else self._container.dbname,
                    "-c",
                    statement,
                ]
            )

    def host_and_port(self) -> tuple[str, int]:
        url = make_url(self._container.get_connection_url(driver="asyncpg"))
        return url.host or "localhost", url.port or 5432


@pytest.fixture
def issuer() -> StubTokenIssuer:
    return StubTokenIssuer()


@pytest.fixture
def clock() -> SteppingClock:
    return SteppingClock()


@pytest.fixture
def store() -> InMemoryStore:
    return seeded_store()


@pytest.fixture
def app(issuer: StubTokenIssuer, store: InMemoryStore, clock: SteppingClock) -> FastAPI:
    return in_memory_app(issuer, store, clock)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with http_client(app) as http:
        yield http


@pytest.fixture
def admin(issuer: StubTokenIssuer) -> dict[str, str]:
    return bearer(issuer, Role.ADMIN)


@pytest.fixture
def customer(issuer: StubTokenIssuer) -> dict[str, str]:
    return bearer(issuer, Role.CUSTOMER)


@pytest.fixture(scope="session")
def alembic_runner() -> AlembicRunner:
    return run_alembic


@pytest.fixture(scope="session")
def create_login_role(postgres_server: PostgresServer) -> Callable[[str, str, str], None]:
    return postgres_server.create_login_role


@pytest.fixture(scope="session")
def postgres_host_and_port(postgres_server: PostgresServer) -> tuple[str, int]:
    return postgres_server.host_and_port()


@pytest.fixture(scope="session")
def postgres_server() -> Iterator[PostgresServer]:
    with PostgresContainer(POSTGRES_IMAGE, driver="asyncpg") as container:
        yield PostgresServer(container)


@pytest.fixture
def empty_database_url(postgres_server: PostgresServer) -> str:
    return postgres_server.create_database()


@pytest.fixture(scope="session")
def migrated_database_url(postgres_server: PostgresServer) -> str:
    url = postgres_server.create_database()
    run_alembic(url, "upgrade", "head")
    return url
