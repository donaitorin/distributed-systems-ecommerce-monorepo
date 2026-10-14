import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from testcontainers.community.postgres import PostgresContainer

CATALOG_DIR = Path(__file__).resolve().parents[1]
POSTGRES_IMAGE = "postgres:17.11-alpine"


type AlembicRunner = Callable[[str, str, str], None]


def run_alembic(database_url: str, action: str, revision: str) -> None:
    config = Config(str(CATALOG_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
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


@pytest.fixture(scope="session")
def alembic_runner() -> AlembicRunner:
    return run_alembic


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
