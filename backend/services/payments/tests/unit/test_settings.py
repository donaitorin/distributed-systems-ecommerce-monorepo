import pytest

from payments.settings import PaymentsSettings, positive_seconds_from_env
from payments.worker import SERVICE_NAME, WorkerSettings

ENVIRON = {
    "PAYMENTS_DB_HOST": "postgres",
    "PAYMENTS_DB_NAME": "payments_db",
    "PAYMENTS_DB_USER": "payments_user",
    "PAYMENTS_DB_PASSWORD": "pw",
    "JWT_JWKS_URL": "http://auth:8000/jwks.json",
    "JWT_ISSUER": "ecommerce-auth",
    "KAFKA_BOOTSTRAP_SERVERS": "kafka:9092",
}


def test_the_api_reads_its_database_and_token_settings() -> None:
    settings = PaymentsSettings.from_env(ENVIRON | {"ROOT_PATH": "/payments-service"})

    assert (settings.database_url.database, settings.database_url.port) == ("payments_db", 5432)
    assert settings.root_path == "/payments-service"


def test_the_late_approval_delay_defaults_to_ninety_seconds() -> None:
    settings = WorkerSettings.from_env(ENVIRON)

    assert settings.late_approval_delay_seconds == 90
    assert settings.settle_interval_seconds == 2
    assert settings.kafka.client_id == SERVICE_NAME == "payments-worker"


def test_both_delays_can_be_shortened_for_tests() -> None:
    settings = WorkerSettings.from_env(
        ENVIRON
        | {"PAYMENT_LATE_APPROVAL_DELAY_SECONDS": "1.5", "PAYMENTS_SETTLE_INTERVAL_SECONDS": "0.1"}
    )

    assert (settings.late_approval_delay_seconds, settings.settle_interval_seconds) == (1.5, 0.1)


@pytest.mark.parametrize("raw", ["0", "-1", "abc", "86401", "nan"])
def test_bad_durations_stop_the_service_at_startup(raw: str) -> None:
    with pytest.raises(ValueError, match="DELAY"):
        positive_seconds_from_env({"DELAY": raw}, "DELAY", 90)


def test_the_kafka_address_is_required_for_the_worker() -> None:
    environ = {key: value for key, value in ENVIRON.items() if key != "KAFKA_BOOTSTRAP_SERVERS"}

    with pytest.raises(KeyError):
        WorkerSettings.from_env(environ)
