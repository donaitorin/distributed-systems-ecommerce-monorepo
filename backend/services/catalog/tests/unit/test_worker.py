from uuid import UUID, uuid4

import pytest
from catalog_testing.imports import SAMPLE, ImportsHarness
from catalog_testing.reservations import (
    NOW,
    add_product,
    cancelled_event,
    created_event,
    line,
    outgoing,
)
from catalog_testing.support import seeded_store
from catalog_testing.test_environment import WORKER_ENVIRON

from catalog.application.reservations import StockReservations
from catalog.domain.imports import ImportStatus
from catalog.infra.memory import InMemoryStore, InMemoryUnitOfWork
from catalog.worker import (
    CONSUMER_GROUP,
    ORDERS_CONSUMER_GROUP,
    SERVICE_NAME,
    WorkerSettings,
    build_orders_consumer,
    import_handlers,
    mark_failed_on_dead_letter,
    order_handlers,
)
from ecommerce_contracts import (
    IMPORT_REQUESTED,
    IMPORT_VALIDATION_REQUESTED,
    ORDER_CANCELLED,
    ORDER_CREATED,
    ORDERS_TOPIC,
    Envelope,
    ImportRequestedV1,
)
from ecommerce_messaging import (
    ClaimMode,
    DeadLetter,
    EventConsumer,
    InMemoryBroker,
    InMemorySource,
)
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


def letter(
    harness: ImportsHarness,
    import_id: UUID,
    with_envelope: bool = True,
    error: str = "boom",
    error_type: str = "ValueError",
) -> DeadLetter:
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
    return DeadLetter(message, envelope, error, error_type, 3, CONSUMER_GROUP)


async def test_a_dead_lettered_import_event_marks_the_import_as_failed() -> None:
    harness = ImportsHarness()
    result = await harness.upload()
    hook = mark_failed_on_dead_letter(harness.jobs)

    await hook(letter(harness, result.record.id))

    failed = await harness.service.get(result.record.id)
    assert failed.status is ImportStatus.FAILED
    assert failed.failure_reason == "ValueError: boom"


async def test_a_failure_reason_that_already_names_the_error_type_is_not_repeated() -> None:
    harness = ImportsHarness()
    result = await harness.upload()
    hook = mark_failed_on_dead_letter(harness.jobs)
    summary = "ImportFileChangedError raised while handling the event"

    await hook(
        letter(harness, result.record.id, error=summary, error_type="ImportFileChangedError")
    )

    failed = await harness.service.get(result.record.id)
    assert failed.failure_reason == summary


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


def order_consumer(store: InMemoryStore) -> tuple[InMemoryBroker, EventConsumer, InMemorySource]:
    broker = InMemoryBroker()
    source = broker.source([ORDERS_TOPIC])
    reservations = StockReservations(lambda: InMemoryUnitOfWork(store), lambda: NOW)
    consumer = build_orders_consumer(reservations, source, broker)
    return broker, consumer, source


async def drain(consumer: EventConsumer, source: InMemorySource) -> None:
    while (message := await source.poll(0)) is not None:
        await consumer.handle(message)


def test_the_worker_reserves_and_releases_for_order_events_in_its_own_group() -> None:
    handlers = order_handlers(StockReservations(lambda: InMemoryUnitOfWork(InMemoryStore())))

    assert {(item.event_type, item.version) for item in handlers} == {
        (ORDER_CREATED, 1),
        (ORDER_CANCELLED, 1),
    }
    assert ORDERS_CONSUMER_GROUP == "catalog-orders"
    assert {item.claim for item in handlers} == {ClaimMode.NONE}


async def test_an_order_created_event_reserves_the_stock_once_even_when_delivered_twice() -> None:
    store = seeded_store()
    sku = await add_product(lambda: InMemoryUnitOfWork(store), stock=3)
    broker, consumer, source = order_consumer(store)
    event = created_event(uuid4(), line(sku, 2))
    await broker.publish(outgoing(event))
    await broker.publish(outgoing(event))

    await drain(consumer, source)

    assert store.products[sku].stock == 1


async def test_an_order_cancelled_before_it_was_created_never_moves_stock() -> None:
    store = seeded_store()
    sku = await add_product(lambda: InMemoryUnitOfWork(store), stock=3)
    broker, consumer, source = order_consumer(store)
    order_id = uuid4()
    await broker.publish(outgoing(cancelled_event(order_id)))
    await broker.publish(outgoing(created_event(order_id, line(sku, 2))))

    await drain(consumer, source)

    assert store.products[sku].stock == 3
    assert store.products[sku].version == 1


async def test_order_events_the_catalog_does_not_handle_are_skipped() -> None:
    store = seeded_store()
    broker, consumer, source = order_consumer(store)
    unknown = created_event(uuid4(), line("X-1")).model_copy(
        update={"event_type": "order.confirmed"}
    )
    await broker.publish(outgoing(unknown))

    await drain(consumer, source)

    assert broker.messages("orders.events.dlq") == []
    assert store.import_data.outbox == []
