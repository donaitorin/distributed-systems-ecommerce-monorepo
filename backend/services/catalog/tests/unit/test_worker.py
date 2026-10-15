from uuid import UUID, uuid4

import pytest
from catalog_testing.imports import SAMPLE, ImportsHarness
from catalog_testing.test_environment import WORKER_ENVIRON

from catalog.domain.imports import ImportStatus
from catalog.worker import (
    CONSUMER_GROUP,
    SERVICE_NAME,
    WorkerSettings,
    import_handlers,
    mark_failed_on_dead_letter,
)
from ecommerce_contracts import (
    IMPORT_REQUESTED,
    IMPORT_VALIDATION_REQUESTED,
    Envelope,
    ImportRequestedV1,
)
from ecommerce_messaging import DeadLetter
from ecommerce_messaging.ports import IncomingMessage


def test_the_worker_reads_catalog_and_kafka_settings_from_the_environment() -> None:
    settings = WorkerSettings.from_env(WORKER_ENVIRON)

    assert settings.kafka.bootstrap_servers == "kafka:9092"
    assert settings.kafka.client_id == SERVICE_NAME
    assert settings.catalog.imports_bucket == "imports"


def test_the_kafka_address_is_required_for_the_worker() -> None:
    environ = {
        key: value for key, value in WORKER_ENVIRON.items() if key != "KAFKA_BOOTSTRAP_SERVERS"
    }

    with pytest.raises(KeyError):
        WorkerSettings.from_env(environ)


def test_the_worker_handles_both_import_events_in_one_consumer_group() -> None:
    handlers = import_handlers(ImportsHarness().jobs)

    assert {(item.event_type, item.version) for item in handlers} == {
        (IMPORT_VALIDATION_REQUESTED, 1),
        (IMPORT_REQUESTED, 1),
    }
    assert CONSUMER_GROUP == "catalog-imports"


def letter(harness: ImportsHarness, import_id: UUID, with_envelope: bool = True) -> DeadLetter:
    envelope = None
    if with_envelope:
        envelope = Envelope[ImportRequestedV1](
            event_type=IMPORT_REQUESTED,
            event_version=1,
            correlation_id=uuid4(),
            producer="catalog-service",
            payload=ImportRequestedV1(
                import_id=import_id,
                object_key="imports/x/source.csv",
                sha256="a" * 64,
            ),
        )
    message = IncomingMessage("imports.jobs", 0, 0, "k", b"{}")
    return DeadLetter(message, envelope, "boom", "ValueError", 3, CONSUMER_GROUP)


async def test_a_dead_lettered_import_event_marks_the_import_as_failed() -> None:
    harness = ImportsHarness()
    result = await harness.upload()
    hook = mark_failed_on_dead_letter(harness.jobs)

    await hook(letter(harness, result.record.id))

    failed = await harness.service.get(result.record.id)
    assert failed.status is ImportStatus.FAILED
    assert failed.failure_reason == "ValueError: boom"


async def test_a_dead_letter_that_could_not_even_be_parsed_changes_nothing() -> None:
    harness = ImportsHarness()
    result = await harness.upload()
    hook = mark_failed_on_dead_letter(harness.jobs)

    await hook(letter(harness, result.record.id, with_envelope=False))

    assert (await harness.service.get(result.record.id)).status is ImportStatus.UPLOADED


def import_event(event_type: str, record: object) -> Envelope[ImportRequestedV1]:
    return Envelope[ImportRequestedV1](
        event_type=event_type,
        event_version=1,
        correlation_id=uuid4(),
        producer="test",
        payload=ImportRequestedV1(
            import_id=record.id,  # type: ignore[attr-defined]
            object_key=record.object_key,  # type: ignore[attr-defined]
            sha256=record.sha256,  # type: ignore[attr-defined]
        ),
    )


async def test_the_registered_handlers_validate_and_process_through_the_jobs() -> None:
    harness = ImportsHarness()
    result = await harness.upload(SAMPLE)
    handlers = {item.event_type: item for item in import_handlers(harness.jobs)}

    await handlers[IMPORT_VALIDATION_REQUESTED].callback(
        import_event(IMPORT_VALIDATION_REQUESTED, result.record), None
    )
    validated = await harness.service.get(result.record.id)
    await harness.service.confirm(result.record.id, uuid4())
    await handlers[IMPORT_REQUESTED].callback(import_event(IMPORT_REQUESTED, result.record), None)

    assert validated.status is ImportStatus.VALIDATED
    assert (await harness.service.get(result.record.id)).status is ImportStatus.COMPLETED
    assert len(harness.store.products) == 88
