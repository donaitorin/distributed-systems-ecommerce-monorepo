import pytest

from ecommerce_messaging import KafkaSettings
from orders.settings import OrdersSettings, positive_seconds_from_env
from orders.worker import SERVICE_NAME, WorkerSettings

ENVIRON = {
    "ORDERS_DB_HOST": "postgres",
    "ORDERS_DB_NAME": "orders_db",
    "ORDERS_DB_USER": "orders_user",
    "ORDERS_DB_PASSWORD": "pw",
    "JWT_JWKS_URL": "http://auth:8000/jwks.json",
    "JWT_ISSUER": "ecommerce-auth",
    "KAFKA_BOOTSTRAP_SERVERS": "kafka:9092",
}


def test_the_api_reads_its_database_and_token_settings() -> None:
    settings = OrdersSettings.from_env(ENVIRON | {"ROOT_PATH": "/orders-service"})

    assert settings.database_url.database == "orders_db"
    assert settings.database_url.port == 5432
    assert settings.root_path == "/orders-service"


def test_the_worker_defaults_to_a_sixty_second_saga_timeout() -> None:
    settings = WorkerSettings.from_env(ENVIRON)

    assert settings.saga_timeout_seconds == 60
    assert settings.sweep_interval_seconds == 5
    assert settings.kafka == KafkaSettings.from_env(ENVIRON, SERVICE_NAME)


def test_the_saga_timeout_and_sweep_interval_are_configurable() -> None:
    settings = WorkerSettings.from_env(
        ENVIRON
        | {"ORDERS_SAGA_TIMEOUT_SECONDS": "1.5", "ORDERS_SAGA_SWEEP_INTERVAL_SECONDS": "0.1"}
    )

    assert (settings.saga_timeout_seconds, settings.sweep_interval_seconds) == (1.5, 0.1)


@pytest.mark.parametrize("raw", ["0", "-1", "abc", "86401", "nan"])
def test_bad_durations_stop_the_service_at_startup(raw: str) -> None:
    with pytest.raises(ValueError, match="TIMEOUT"):
        positive_seconds_from_env({"TIMEOUT": raw}, "TIMEOUT", 60)


def test_the_kafka_address_is_required_for_the_worker() -> None:
    environ = {key: value for key, value in ENVIRON.items() if key != "KAFKA_BOOTSTRAP_SERVERS"}

    with pytest.raises(KeyError):
        WorkerSettings.from_env(environ)
