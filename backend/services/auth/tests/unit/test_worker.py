import pytest

from auth.infra.database import create_engine, create_session_factory
from auth.infra.models import OUTBOX
from auth.worker import SERVICE_NAME, WorkerSettings, build_relay
from ecommerce_messaging import InMemoryBroker, OutboxRelay

ENVIRON = {
    "AUTH_DB_HOST": "postgres",
    "AUTH_DB_NAME": "auth_db",
    "AUTH_DB_USER": "auth_user",
    "AUTH_DB_PASSWORD": "pw",
    "KAFKA_BOOTSTRAP_SERVERS": "kafka:9092",
}


def test_the_worker_reads_auth_and_kafka_settings_from_the_environment() -> None:
    settings = WorkerSettings.from_env(ENVIRON)

    assert settings.kafka.bootstrap_servers == "kafka:9092"
    assert settings.kafka.client_id == SERVICE_NAME == "auth-worker"
    assert settings.auth.database_url.database == "auth_db"


def test_the_worker_does_not_need_signing_keys_or_jwt_settings() -> None:
    assert WorkerSettings.from_env(ENVIRON).auth.keys_dir.as_posix() == "/keys"


def test_the_kafka_address_is_required_for_the_worker() -> None:
    environ = {key: value for key, value in ENVIRON.items() if key != "KAFKA_BOOTSTRAP_SERVERS"}

    with pytest.raises(KeyError):
        WorkerSettings.from_env(environ)


def test_the_outbox_table_is_the_one_the_migration_creates() -> None:
    assert OUTBOX.name == "outbox"
    assert {"event_id", "topic", "key", "payload", "published_at"} <= set(OUTBOX.c.keys())


async def test_build_relay_drains_the_outbox_table_into_the_publisher() -> None:
    engine = create_engine("postgresql+asyncpg://auth_user:pw@127.0.0.1:1/auth_db")
    try:
        relay = build_relay(create_session_factory(engine), InMemoryBroker())
    finally:
        await engine.dispose()

    assert isinstance(relay, OutboxRelay)
