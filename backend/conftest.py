from collections.abc import Iterator

import pytest

from kafka_support import KafkaBroker, free_port, run_kafka
from postgres_support import PostgresServer, run_postgres
from seaweedfs_support import SeaweedFs, run_seaweedfs


@pytest.fixture(scope="session")
def seaweedfs() -> Iterator[SeaweedFs]:
    with run_seaweedfs() as server:
        yield server


@pytest.fixture(scope="session")
def postgres_server() -> Iterator[PostgresServer]:
    with run_postgres() as server:
        yield server


@pytest.fixture(scope="session")
def kafka() -> Iterator[KafkaBroker]:
    with run_kafka() as broker:
        yield broker


@pytest.fixture
def stoppable_kafka() -> Iterator[KafkaBroker]:
    broker = KafkaBroker(free_port())
    broker.start()
    try:
        yield broker
    finally:
        broker.stop()
