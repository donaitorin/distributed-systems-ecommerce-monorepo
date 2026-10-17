import logging
from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import UUID

import pytest
from cart_testing.events import confirmed_event, deleted_event, message_of, updated_event
from cart_testing.support import Stores, product

from cart.application.errors import CartError
from cart.application.purchases import PurchasedLines
from cart.domain.cart import CartLine
from cart.domain.product import ProductState
from cart.infra.memory import InMemoryCartStore
from cart.worker import (
    CONSUMER_GROUP,
    ORDERS_CONSUMER_GROUP,
    PATIENT_RETRY,
    SERVICE_NAME,
    WorkerSettings,
    build_consumer,
    build_purchase_consumer,
    build_source,
    log_dead_letter,
    purchase_handlers,
)
from ecommerce_messaging import (
    ClaimMode,
    DeadLetter,
    InMemoryBroker,
    Outcome,
    OutgoingMessage,
    RetryPolicy,
)

ENVIRON = {
    "REDIS_CART_HOST": "redis-cart",
    "REDIS_CART_PASSWORD": "secret",
    "KAFKA_BOOTSTRAP_SERVERS": "kafka:9092",
}
TOPIC = "catalog.events"


def test_the_worker_reads_redis_and_kafka_settings_without_any_jwt_variables() -> None:
    settings = WorkerSettings.from_env(ENVIRON)

    assert (settings.redis.host, settings.redis.port) == ("redis-cart", 6379)
    assert settings.kafka.bootstrap_servers == "kafka:9092"
    assert settings.kafka.client_id == SERVICE_NAME == "cart-worker"
    assert (settings.topic, settings.group) == (TOPIC, "cart-catalog-events")
    assert CONSUMER_GROUP == "cart-catalog-events"
    assert (settings.ttl_seconds, settings.log_level) == (30 * 24 * 3600, "INFO")


def test_the_log_level_and_ttl_can_be_set() -> None:
    settings = WorkerSettings.from_env(ENVIRON | {"LOG_LEVEL": "DEBUG", "CART_TTL_SECONDS": "60"})

    assert (settings.log_level, settings.ttl_seconds) == ("DEBUG", 60)


@pytest.mark.parametrize("missing", ["REDIS_CART_HOST", "KAFKA_BOOTSTRAP_SERVERS"])
def test_redis_and_kafka_addresses_are_required(missing: str) -> None:
    environ = {key: value for key, value in ENVIRON.items() if key != missing}

    with pytest.raises(KeyError):
        WorkerSettings.from_env(environ)


def test_the_retry_policy_outlasts_a_restart_of_redis() -> None:
    waited = sum(PATIENT_RETRY.delay(attempt) for attempt in range(1, PATIENT_RETRY.max_attempts))

    assert PATIENT_RETRY.max_attempts == 8
    assert waited >= 20


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
    assert consumer.topics == (TOPIC,)
    assert consumer.options["group_id"] == "cart-catalog-events"
    assert consumer.options["auto_offset_reset"] == "earliest"
    assert consumer.options["enable_auto_commit"] is False


class Rig:
    def __init__(self, retry: RetryPolicy = PATIENT_RETRY) -> None:
        self.stores = Stores()
        self.broker = InMemoryBroker()
        self.sleeps: list[float] = []
        self.consumer = build_consumer(
            self.broker.source([TOPIC]),
            self.broker,
            self.stores.projection,
            retry=retry,
            sleep=self.sleep,
        )

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)

    async def reserve(self, state: ProductState | None = None) -> None:
        await self.stores.projection.reserve("RS-001")
        if state is not None:
            await self.stores.projection.apply_state(state)

    async def deliver(self, event: Any, offset: int = 0) -> Outcome:
        return await self.consumer.handle(message_of(event, offset))

    def stored(self) -> ProductState | None:
        return self.stores.projection.entries.get("RS-001")


async def test_an_update_event_reaches_the_projection() -> None:
    rig = Rig()
    await rig.reserve()

    outcome = await rig.deliver(updated_event(version=2, price="79.90", stock=5))

    assert outcome is Outcome.PROCESSED
    assert rig.stored() == product(version=2, price="79.90", stock=5, image_key=None)


async def test_a_deletion_event_flags_the_product() -> None:
    rig = Rig()
    await rig.reserve(product(version=2))

    await rig.deliver(deleted_event(version=3))

    state = rig.stored()
    assert state is not None
    assert (state.deleted, state.version) == (True, 3)


async def test_the_same_event_delivered_twice_is_applied_once() -> None:
    rig = Rig()
    await rig.reserve()
    event = updated_event(version=2, price="79.90")

    await rig.deliver(event, 0)
    first = rig.stored()
    await rig.deliver(event, 1)

    assert rig.stored() == first


async def test_events_delivered_out_of_order_end_in_the_newest_state() -> None:
    rig = Rig()
    await rig.reserve()

    for offset, version in enumerate((4, 2, 5, 3, 1)):
        await rig.deliver(updated_event(version=version, price=f"{version}.00"), offset)

    state = rig.stored()
    assert state is not None
    assert (state.version, str(state.price)) == (5, "5.00")


async def test_a_late_update_does_not_resurrect_a_deleted_product() -> None:
    rig = Rig()
    await rig.reserve()

    await rig.deliver(deleted_event(version=4), 0)
    await rig.deliver(updated_event(version=3), 1)

    state = rig.stored()
    assert state is not None
    assert state.deleted is True


async def test_events_for_products_in_no_cart_leave_the_projection_empty() -> None:
    rig = Rig()

    for number in range(50):
        await rig.deliver(updated_event(sku=f"IMPORT-{number}"), number)
    await rig.deliver(deleted_event(sku="IMPORT-1"), 99)

    assert rig.stores.projection.entries == {}


async def test_other_event_types_on_the_topic_are_skipped() -> None:
    rig = Rig()
    other = updated_event().model_copy(update={"event_type": "product.reviewed"})

    assert await rig.deliver(other) is Outcome.IGNORED


async def test_an_unsupported_version_or_a_malformed_message_is_dead_lettered() -> None:
    rig = Rig()
    future = updated_event().model_copy(update={"event_version": 2})
    garbage = message_of(updated_event())
    garbage = type(garbage)(TOPIC, 0, 1, "RS-001", b"{not json")

    assert await rig.deliver(future) is Outcome.DEAD_LETTERED
    assert await rig.consumer.handle(garbage) is Outcome.DEAD_LETTERED
    assert len(rig.broker.messages(TOPIC + ".dlq")) == 2


class FlakyProjection:
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.applied: list[int] = []

    async def apply_state(self, state: ProductState) -> bool:
        if self.failures:
            self.failures -= 1
            raise CartError("redis restarting")
        self.applied.append(state.version)
        return True

    async def apply_deletion(self, sku: str, version: int) -> bool:
        return True

    async def reserve(self, sku: str) -> None:
        return None

    async def read_many(self, skus: list[str]) -> dict[str, ProductState]:
        return {}


async def test_a_store_that_is_down_for_a_while_does_not_lose_the_event() -> None:
    broker = InMemoryBroker()
    flaky = FlakyProjection(failures=6)
    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    consumer = build_consumer(broker.source([TOPIC]), broker, flaky, sleep=sleep)

    outcome = await consumer.handle(message_of(updated_event(version=7)))

    assert outcome is Outcome.PROCESSED
    assert flaky.applied == [7]
    assert len(sleeps) == 6
    assert broker.messages(TOPIC + ".dlq") == []


async def test_an_event_that_keeps_failing_ends_in_the_dead_letter_topic() -> None:
    broker = InMemoryBroker()
    flaky = FlakyProjection(failures=100)

    async def sleep(seconds: float) -> None:
        return None

    consumer = build_consumer(broker.source([TOPIC]), broker, flaky, sleep=sleep)

    outcome = await consumer.handle(message_of(updated_event(version=7)))

    assert outcome is Outcome.DEAD_LETTERED
    [dead] = broker.messages(TOPIC + ".dlq")
    assert dead.headers["x-attempts"] == b"8"


async def test_a_dead_letter_logs_identifiers_but_not_the_error_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    envelope = updated_event(name="Secret product")
    letter = DeadLetter(
        message_of(envelope, 7), envelope, "boom Secret product", "ValueError", 8, CONSUMER_GROUP
    )

    with caplog.at_level(logging.WARNING, logger="cart.worker"):
        await log_dead_letter(letter)

    [record] = [r for r in caplog.records if r.name == "cart.worker"]
    assert record.__dict__["event_id"] == str(envelope.event_id)
    assert record.__dict__["event_type"] == "product.updated"
    assert (record.__dict__["topic"], record.__dict__["offset"]) == (TOPIC, 7)
    assert "Secret product" not in caplog.text
    assert "boom" not in caplog.text


async def test_a_dead_letter_without_an_envelope_still_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    letter = DeadLetter(
        message_of(updated_event()), None, "not json", "InvalidEventError", 0, CONSUMER_GROUP
    )

    with caplog.at_level(logging.WARNING, logger="cart.worker"):
        await log_dead_letter(letter)

    [record] = [r for r in caplog.records if r.name == "cart.worker"]
    assert (record.__dict__["event_id"], record.__dict__["event_type"]) == (None, None)


def test_the_cart_worker_also_listens_to_order_events_in_its_own_group() -> None:
    settings = WorkerSettings.from_env(ENVIRON)

    assert (settings.orders_topic, settings.orders_group) == ("orders.events", "cart-order-events")
    assert ORDERS_CONSUMER_GROUP == "cart-order-events"


def test_the_purchase_handler_is_idempotent_by_itself() -> None:
    [handler] = purchase_handlers(PurchasedLines(InMemoryCartStore()))

    assert (handler.event_type, handler.version, handler.claim) == (
        "order.confirmed",
        1,
        ClaimMode.NONE,
    )


async def test_a_confirmed_order_empties_its_lines_through_the_consumer() -> None:
    store = InMemoryCartStore()
    broker = InMemoryBroker()
    source = broker.source(["orders.events"])
    consumer = build_purchase_consumer(source, broker, store, sleep=no_sleep)
    customer = UUID(int=5)
    when = datetime(2026, 10, 1, tzinfo=UTC)
    for sku in ("A-1", "B-2"):
        await store.put_line(str(customer), CartLine.started(product(sku=sku), 1, when), 100)
    event = confirmed_event(customer, ["A-1"])
    outgoing = OutgoingMessage("orders.events", "k", event.model_dump_json().encode())
    await broker.publish(outgoing)
    await broker.publish(outgoing)

    while (message := await source.poll(0)) is not None:
        await consumer.handle(message)

    assert [line.sku for line in await store.lines(str(customer))] == ["B-2"]
    assert broker.messages("orders.events.dlq") == []


async def no_sleep(_: float) -> None:
    return None
