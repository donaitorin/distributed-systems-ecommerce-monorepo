import pytest

from ecommerce_messaging import KafkaSettings


def test_settings_read_the_bootstrap_servers_and_default_the_rest() -> None:
    settings = KafkaSettings.from_env({"KAFKA_BOOTSTRAP_SERVERS": "kafka:9092"}, "catalog")

    assert settings.bootstrap_servers == "kafka:9092"
    assert settings.client_id == "catalog"
    assert settings.max_poll_interval_ms == 1_800_000
    assert settings.publish_timeout_seconds == 15.0


def test_the_poll_interval_can_be_configured() -> None:
    settings = KafkaSettings.from_env(
        {"KAFKA_BOOTSTRAP_SERVERS": "kafka:9092", "KAFKA_MAX_POLL_INTERVAL_MS": "60000"}
    )

    assert settings.max_poll_interval_ms == 60000


def test_the_bootstrap_servers_are_required() -> None:
    with pytest.raises(KeyError):
        KafkaSettings.from_env({})
