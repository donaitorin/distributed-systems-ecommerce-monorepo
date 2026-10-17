from collections.abc import AsyncIterator, Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from payments_testing.data import SteppingClock

from payments.application.ports import UnitOfWorkFactory
from payments.infra.database import create_engine, create_session_factory
from payments.infra.memory import InMemoryStore, InMemoryUnitOfWork
from payments.infra.unit_of_work import SqlAlchemyUnitOfWork
from postgres_support import PostgresServer

PAYMENTS_DIR = Path(__file__).resolve().parents[1]

type AlembicRunner = Callable[[str, str, str], None]


def run_alembic(database_url: str, action: str, revision: str) -> None:
    config = Config(str(PAYMENTS_DIR / "alembic.ini"))
    config.attributes["database_url"] = database_url
    config.attributes["configure_logging"] = False
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(getattr(command, action), config, revision).result()


@pytest.fixture
def clock() -> SteppingClock:
    return SteppingClock()


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture(scope="session")
def alembic_runner() -> AlembicRunner:
    return run_alembic


@pytest.fixture
def empty_database_url(postgres_server: PostgresServer) -> str:
    return postgres_server.create_database()


@pytest.fixture(scope="session")
def migrated_database_url(postgres_server: PostgresServer) -> str:
    url = postgres_server.create_database()
    run_alembic(url, "upgrade", "head")
    return url


@pytest.fixture(
    params=["memory", pytest.param("sql", marks=pytest.mark.integration)],
)
async def unit_of_work(request: pytest.FixtureRequest) -> AsyncIterator[UnitOfWorkFactory]:
    if request.param == "memory":
        store = InMemoryStore()
        yield lambda: InMemoryUnitOfWork(store)
        return
    url: str = request.getfixturevalue("migrated_database_url")
    engine = create_engine(url)
    session_factory = create_session_factory(engine)
    yield lambda: SqlAlchemyUnitOfWork(session_factory)
    await engine.dispose()
