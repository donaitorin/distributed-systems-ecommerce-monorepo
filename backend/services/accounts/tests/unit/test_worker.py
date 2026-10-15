import logging
from typing import Any, ClassVar
from uuid import uuid4

import pytest
from accounts_testing.data import START
from accounts_testing.events import incoming, registered_event
from sqlalchemy import URL

from accounts.worker import (
    CONSUMER_GROUP,
    SERVICE_NAME,
    WorkerSettings,
    build_source,
    log_dead_letter,
)
from ecommerce_messaging import DeadLetter

ENVIRON = {
    "ACCOUNTS_DB_HOST": "postgres",
    "ACCOUNTS_DB_NAME": "accounts_db",
    "ACCOUNTS_DB_USER": "accounts_user",
    "ACCOUNTS_DB_PASSWORD": "pw",
    "KAFKA_BOOTSTRAP_SERVERS": "kafka:9092",
}


def test_the_worker_reads_database_and_kafka_settings_without_any_jwt_variables() -> None:
    settings = WorkerSettings.from_env(ENVIRON)

    assert isinstance(settings.database_url, URL)
    assert settings.database_url.database == "accounts_db"
    assert settings.kafka.bootstrap_servers == "kafka:9092"
    assert settings.kafka.client_id == SERVICE_NAME == "accounts-worker"
    assert (settings.topic, settings.group) == ("auth.events", "accounts-auth-events")
    assert CONSUMER_GROUP == "accounts-auth-events"
    assert settings.log_level == "INFO"


def test_the_log_level_can_be_set() -> None:
    assert WorkerSettings.from_env(ENVIRON | {"LOG_LEVEL": "DEBUG"}).log_level == "DEBUG"


def test_the_kafka_address_is_required_for_the_worker() -> None:
    environ = {key: value for key, value in ENVIRON.items() if key != "KAFKA_BOOTSTRAP_SERVERS"}

    with pytest.raises(KeyError):
        WorkerSettings.from_env(environ)


class RecordingConsumer:
    created: ClassVar[list["RecordingConsumer"]] = []

    def __init__(self, *topics: str, **options: Any) -> None:
        self.topics = topics
        self.options = options
        RecordingConsumer.created.append(self)

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def getmany(self, **_: Any) -> dict[Any, Any]:
        return {}


async def test_a_new_group_starts_from_the_earliest_offset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    RecordingConsumer.created.clear()
    monkeypatch.setattr("ecommerce_messaging.kafka.AIOKafkaConsumer", RecordingConsumer)
    source = build_source(WorkerSettings.from_env(ENVIRON))

    await source.poll(0)
    await source.close()

    [consumer] = RecordingConsumer.created
    assert consumer.topics == ("auth.events",)
    assert consumer.options["group_id"] == "accounts-auth-events"
    assert consumer.options["auto_offset_reset"] == "earliest"
    assert consumer.options["enable_auto_commit"] is False


ENVELOPE = registered_event(uuid4(), START, email="ada@example.com")


def dead_letter(with_envelope: bool, error: str = "boom with ada@example.com") -> DeadLetter:
    message = incoming(ENVELOPE, offset=7)
    return DeadLetter(
        message, ENVELOPE if with_envelope else None, error, "ValueError", 3, CONSUMER_GROUP
    )


async def test_a_dead_letter_with_an_envelope_logs_one_warning_with_its_identifiers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="accounts.worker"):
        await log_dead_letter(dead_letter(True))

    [record] = [r for r in caplog.records if r.name == "accounts.worker"]
    assert record.levelno == logging.WARNING
    assert record.__dict__["event_id"] == str(ENVELOPE.event_id)
    assert record.__dict__["event_type"] == "user.registered"
    assert (record.__dict__["topic"], record.__dict__["offset"]) == ("auth.events", 7)
    assert record.__dict__["attempts"] == 3
    assert record.__dict__["error_type"] == "ValueError"


async def test_a_dead_letter_that_could_not_be_parsed_still_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="accounts.worker"):
        await log_dead_letter(dead_letter(False))

    [record] = [r for r in caplog.records if r.name == "accounts.worker"]
    assert record.__dict__["event_id"] is None
    assert record.__dict__["event_type"] is None


async def test_the_dead_letter_log_never_contains_the_error_text_or_the_email(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="accounts.worker"):
        await log_dead_letter(dead_letter(True))

    assert "ada@example.com" not in caplog.text
    assert "boom" not in caplog.text
