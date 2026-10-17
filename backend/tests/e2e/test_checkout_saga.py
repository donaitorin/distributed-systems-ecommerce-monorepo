import asyncio
import contextlib
import dataclasses
import json
from collections.abc import AsyncIterator, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from aiokafka import AIOKafkaConsumer
from alembic import command
from alembic.config import Config
from catalog_testing.test_environment import WORKER_ENVIRON
from orders_testing.data import ADDRESS, order_body
from orders_testing.support import bearer, http_client, orders_settings
from orders_testing.waiting import eventually
from payments_testing.support import payments_settings
from redis.asyncio import Redis
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

import catalog.worker as catalog_worker
import orders.worker as orders_worker
import payments.worker as payments_worker
from cart.domain.cart import CartLine
from cart.domain.product import ProductState
from cart.infra.redis_store import RedisCartStore
from cart.settings import RedisSettings
from cart.worker import WorkerSettings as CartWorkerSettings
from cart.worker import run_worker as run_cart_worker
from catalog.domain.product import NewProduct, ProductData
from catalog.infra.database import create_session_factory as catalog_sessions
from catalog.infra.unit_of_work import SqlAlchemyUnitOfWork as CatalogUnitOfWork
from catalog.settings import CatalogSettings
from ecommerce_auth.testing import StubTokenIssuer, build_stub_verifier
from ecommerce_messaging import KafkaSettings
from kafka_support import KafkaBroker, run_kafka
from orders.main import create_orders_app
from payments.main import create_payments_app
from postgres_support import PostgresServer
from redis_support import PASSWORD, RedisServer

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="module"),
]

BACKEND = Path(__file__).resolve().parents[2]
SAGA_TIMEOUT_SECONDS = 8.0
LATE_APPROVAL_SECONDS = 12.0
TOPICS = ["orders.events", "inventory.events", "payments.events", "catalog.events"]
CART_TTL = 3600
WAIT_SECONDS = 90


def migrate(service: str, url: str) -> None:
    config = Config(str(BACKEND / "services" / service / "alembic.ini"))
    config.attributes["database_url"] = url
    config.attributes["configure_logging"] = False
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(command.upgrade, config, "head").result()


@dataclass(slots=True)
class Infrastructure:
    kafka: KafkaBroker
    catalog_url: str
    orders_url: str
    payments_url: str
    redis: RedisServer


@dataclass(slots=True)
class Saga:
    infrastructure: Infrastructure
    issuer: StubTokenIssuer
    catalog: Any
    catalog_engine: AsyncEngine
    orders_engine: AsyncEngine
    payments_engine: AsyncEngine
    redis: Redis
    carts: RedisCartStore
    orders_client: httpx.AsyncClient
    payments_client: httpx.AsyncClient
    events: list[dict[str, Any]] = field(default_factory=list)

    def catalog_work(self) -> CatalogUnitOfWork:
        return CatalogUnitOfWork(self.catalog)

    async def add_product(self, price: str = "10.00", stock: int = 5) -> str:
        sku = f"E2E-{uuid4().hex[:10].upper()}"
        data = ProductData("Saga Widget", None, None, Decimal(price), stock, None)
        async with self.catalog_work() as uow:
            await uow.products.add(NewProduct(sku, data), datetime.now(UTC))
            await uow.commit()
        return sku

    async def stock(self, sku: str) -> int:
        async with self.catalog_work() as uow:
            product = await uow.products.get(sku)
        assert product is not None
        return product.stock

    async def put_in_cart(self, customer: UUID, sku: str) -> None:
        state = ProductState(sku, "Saga Widget", Decimal("10.00"), 5, 1, False, None)
        line = CartLine.started(state, 2, datetime.now(UTC))
        await self.carts.put_line(str(customer), line, 100)

    async def cart_skus(self, customer: UUID) -> list[str]:
        return [line.sku for line in await self.carts.lines(str(customer))]

    async def place(
        self,
        customer: UUID,
        sku: str,
        card: str,
        quantity: int = 2,
        price: str = "10.00",
        key: str | None = None,
    ) -> httpx.Response:
        body = order_body(
            lines=[{"sku": sku, "quantity": quantity, "unit_price": price}],
            shipping_address=dict(ADDRESS),
            payment={"card_number": f"4929 1234 5678 {card}"},
        )
        headers = bearer(self.issuer, customer) | {"Idempotency-Key": key or f"e2e-{uuid4().hex}"}
        return await self.orders_client.post("/api/v1/orders", json=body, headers=headers)

    async def order(self, customer: UUID, order_id: str) -> dict[str, Any]:
        response = await self.orders_client.get(
            f"/api/v1/orders/{order_id}", headers=bearer(self.issuer, customer)
        )
        assert response.status_code == 200
        body: dict[str, Any] = response.json()
        return body

    async def wait_for_status(self, customer: UUID, order_id: str, status: str) -> dict[str, Any]:
        async def reached() -> bool:
            return bool((await self.order(customer, order_id))["status"] == status)

        await eventually(reached, seconds=WAIT_SECONDS, interval=0.2)
        return await self.order(customer, order_id)

    async def payment(self, customer: UUID, order_id: str) -> dict[str, Any] | None:
        response = await self.payments_client.get(
            f"/api/v1/payments/{order_id}", headers=bearer(self.issuer, customer)
        )
        if response.status_code == 404:
            return None
        body: dict[str, Any] = response.json()
        return body

    async def wait_for_payment(self, customer: UUID, order_id: str, status: str) -> dict[str, Any]:
        async def reached() -> bool:
            payment = await self.payment(customer, order_id)
            return payment is not None and payment["status"] == status

        await eventually(reached, seconds=WAIT_SECONDS, interval=0.2)
        found = await self.payment(customer, order_id)
        assert found is not None
        return found

    async def correlation_of(self, order_id: str) -> str:
        async with self.orders_engine.connect() as connection:
            result = await connection.execute(
                text("SELECT correlation_id FROM orders WHERE id = :id"), {"id": UUID(order_id)}
            )
            return str(result.scalar_one())

    def events_of(self, correlation_id: str) -> list[dict[str, Any]]:
        return [event for event in self.events if event["correlation_id"] == correlation_id]

    async def wait_for_events(self, correlation_id: str, wanted: set[str]) -> list[str]:
        def seen() -> bool:
            return wanted <= {event["event_type"] for event in self.events_of(correlation_id)}

        await eventually(seen, seconds=WAIT_SECONDS, interval=0.2)
        return [event["event_type"] for event in self.events_of(correlation_id)]


@pytest.fixture(scope="module")
def infrastructure(
    postgres_server: PostgresServer, redis_server: RedisServer
) -> Iterator[Infrastructure]:
    with run_kafka() as broker:
        urls = [postgres_server.create_database() for _ in range(3)]
        for service, url in zip(("catalog", "orders", "payments"), urls, strict=True):
            migrate(service, url)
        yield Infrastructure(broker, urls[0], urls[1], urls[2], redis_server)


async def collect_events(
    kafka: KafkaBroker, sink: list[dict[str, Any]], stop: asyncio.Event
) -> None:
    reader = AIOKafkaConsumer(
        *TOPICS,
        bootstrap_servers=kafka.bootstrap,
        group_id=f"e2e-reader-{uuid4().hex}",
        auto_offset_reset="earliest",
    )
    await reader.start()
    try:
        while not stop.is_set():
            for records in (await reader.getmany(timeout_ms=300)).values():
                for record in records:
                    event = json.loads(record.value)
                    event["topic"] = record.topic
                    sink.append(event)
    finally:
        await reader.stop()


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def saga(infrastructure: Infrastructure) -> AsyncIterator[Saga]:
    kafka = infrastructure.kafka
    kafka_settings = KafkaSettings(kafka.bootstrap, "e2e", publish_timeout_seconds=10)
    catalog_engine = create_async_engine(infrastructure.catalog_url, pool_size=10)
    orders_engine = create_async_engine(infrastructure.orders_url, pool_size=10)
    payments_engine = create_async_engine(infrastructure.payments_url, pool_size=10)
    redis = Redis(
        port=infrastructure.redis.port, password=PASSWORD, decode_responses=True, socket_timeout=5
    )
    issuer = StubTokenIssuer()
    orders_app = create_orders_app(orders_settings(), orders_engine)
    orders_app.state.token_verifier = build_stub_verifier(issuer)
    payments_app = create_payments_app(payments_settings(), payments_engine)
    payments_app.state.token_verifier = build_stub_verifier(issuer)
    events: list[dict[str, Any]] = []
    stop = asyncio.Event()
    catalog_settings = dataclasses.replace(
        CatalogSettings.from_env(WORKER_ENVIRON), database_url=make_url(infrastructure.catalog_url)
    )
    workers = [
        asyncio.create_task(
            catalog_worker.run_worker(
                catalog_worker.WorkerSettings(catalog_settings, kafka_settings), stop
            )
        ),
        asyncio.create_task(
            orders_worker.run_worker(
                orders_worker.WorkerSettings(
                    make_url(infrastructure.orders_url),
                    kafka_settings,
                    saga_timeout_seconds=SAGA_TIMEOUT_SECONDS,
                    sweep_interval_seconds=0.3,
                ),
                stop,
            )
        ),
        asyncio.create_task(
            payments_worker.run_worker(
                payments_worker.WorkerSettings(
                    make_url(infrastructure.payments_url),
                    kafka_settings,
                    late_approval_delay_seconds=LATE_APPROVAL_SECONDS,
                    settle_interval_seconds=0.3,
                ),
                stop,
            )
        ),
        asyncio.create_task(
            run_cart_worker(
                CartWorkerSettings(
                    redis=RedisSettings(
                        host="127.0.0.1", port=infrastructure.redis.port, password=PASSWORD
                    ),
                    kafka=kafka_settings,
                    ttl_seconds=CART_TTL,
                ),
                stop,
            )
        ),
        asyncio.create_task(collect_events(kafka, events, stop)),
    ]
    async with (
        http_client(orders_app) as orders_client,
        http_client(payments_app) as payments_client,
    ):
        yield Saga(
            infrastructure,
            issuer,
            catalog_sessions(catalog_engine),
            catalog_engine,
            orders_engine,
            payments_engine,
            redis,
            RedisCartStore(redis, CART_TTL),
            orders_client,
            payments_client,
            events,
        )
        stop.set()
        done, pending = await asyncio.wait(workers, timeout=60)
        for task in pending:
            task.cancel()
        for task in done:
            with contextlib.suppress(Exception):
                task.result()
    await redis.aclose()
    for engine in (catalog_engine, orders_engine, payments_engine):
        await engine.dispose()


def history_of(order: dict[str, Any]) -> list[tuple[str | None, str, str | None]]:
    return [(h["from_status"], h["to_status"], h["reason"]) for h in order["history"]]


async def test_an_approved_card_confirms_the_order_takes_the_stock_and_empties_the_cart_line(
    saga: Saga,
) -> None:
    customer, sku = uuid4(), await saga.add_product(stock=5)
    other = await saga.add_product()
    await saga.put_in_cart(customer, sku)
    await saga.put_in_cart(customer, other)

    placed = await saga.place(customer, sku, "1111")
    order_id = placed.json()["id"]
    order = await saga.wait_for_status(customer, order_id, "CONFIRMED")
    payment = await saga.payment(customer, order_id)

    assert placed.status_code == 202
    assert [(a, b) for a, b, _ in history_of(order)] == [
        (None, "PENDING"),
        ("PENDING", "STOCK_RESERVED"),
        ("STOCK_RESERVED", "PAID"),
        ("PAID", "CONFIRMED"),
    ]
    assert order["lines"][0]["name"] == "Saga Widget"
    assert await saga.stock(sku) == 3
    assert payment is not None
    assert (payment["status"], payment["card_last4"], payment["amount"]) == (
        "SUCCEEDED",
        "1111",
        "20.00",
    )

    async def purchased_line_is_gone() -> bool:
        return await saga.cart_skus(customer) == [other]

    await eventually(purchased_line_is_gone, seconds=WAIT_SECONDS, interval=0.2)


async def test_one_order_can_be_followed_across_the_topics_by_its_correlation_id(
    saga: Saga,
) -> None:
    customer, sku = uuid4(), await saga.add_product()
    order_id = (await saga.place(customer, sku, "1111")).json()["id"]
    await saga.wait_for_status(customer, order_id, "CONFIRMED")
    correlation = await saga.correlation_of(order_id)

    await saga.wait_for_events(
        correlation,
        {
            "order.created",
            "stock.reserved",
            "order.payment_requested",
            "payment.succeeded",
            "order.confirmed",
            "product.updated",
        },
    )

    events = saga.events_of(correlation)
    by_topic = {(event["topic"], event["event_type"]) for event in events}
    assert ("orders.events", "order.created") in by_topic
    assert ("inventory.events", "stock.reserved") in by_topic
    assert ("payments.events", "payment.succeeded") in by_topic
    assert ("catalog.events", "product.updated") in by_topic
    assert {event["payload"].get("order_id", order_id) for event in events} == {order_id}


async def test_a_declined_card_cancels_the_order_and_gives_the_stock_back(saga: Saga) -> None:
    customer, sku = uuid4(), await saga.add_product(stock=5)
    await saga.put_in_cart(customer, sku)

    order_id = (await saga.place(customer, sku, "0000")).json()["id"]
    order = await saga.wait_for_status(customer, order_id, "CANCELLED")

    async def stock_is_back() -> bool:
        return await saga.stock(sku) == 5

    await eventually(stock_is_back, seconds=WAIT_SECONDS, interval=0.2)
    payment = await saga.payment(customer, order_id)
    events = await saga.wait_for_events(
        await saga.correlation_of(order_id), {"stock.released", "payment.failed", "order.cancelled"}
    )

    assert order["cancel_reason"] == "payment_failed"
    assert ("STOCK_RESERVED", "CANCELLED", "payment_failed") in history_of(order)
    assert payment is not None
    assert (payment["status"], payment["failure_reason"]) == ("FAILED", "card_declined")
    assert "payment.refunded" not in events
    assert await saga.cart_skus(customer) == [sku]


async def test_a_card_that_never_answers_is_cancelled_by_the_timeout_and_the_stock_returns(
    saga: Saga,
) -> None:
    customer, sku = uuid4(), await saga.add_product(stock=5)
    await saga.put_in_cart(customer, sku)
    order_id = (await saga.place(customer, sku, "9999")).json()["id"]

    stalled = await saga.wait_for_status(customer, order_id, "STOCK_RESERVED")
    assert await saga.stock(sku) == 3
    order = await saga.wait_for_status(customer, order_id, "CANCELLED")

    async def stock_is_back() -> bool:
        return await saga.stock(sku) == 5

    await eventually(stock_is_back, seconds=WAIT_SECONDS, interval=0.2)
    payment = await saga.payment(customer, order_id)
    assert stalled["status"] == "STOCK_RESERVED"
    assert order["cancel_reason"] == "saga_timeout"
    assert payment is not None
    assert payment["status"] == "PENDING"
    assert await saga.cart_skus(customer) == [sku]


async def test_a_late_approval_after_the_timeout_is_refunded_and_the_order_stays_cancelled(
    saga: Saga,
) -> None:
    customer, sku = uuid4(), await saga.add_product(stock=5)
    order_id = (await saga.place(customer, sku, "2222")).json()["id"]

    cancelled = await saga.wait_for_status(customer, order_id, "CANCELLED")
    still_pending = await saga.payment(customer, order_id)
    refunded = await saga.wait_for_payment(customer, order_id, "REFUNDED")

    async def refund_is_in_the_order() -> bool:
        return (await saga.order(customer, order_id))["refunded_at"] is not None

    await eventually(refund_is_in_the_order, seconds=WAIT_SECONDS, interval=0.2)
    order = await saga.order(customer, order_id)
    events = await saga.wait_for_events(
        await saga.correlation_of(order_id), {"payment.succeeded", "payment.refunded"}
    )

    assert cancelled["cancel_reason"] == "saga_timeout"
    assert still_pending is not None
    assert still_pending["status"] == "PENDING"
    assert refunded["refunded_at"] is not None
    assert order["status"] == "CANCELLED"
    assert history_of(order)[-2:] == [
        ("STOCK_RESERVED", "CANCELLED", "saga_timeout"),
        ("CANCELLED", "CANCELLED", "payment refunded"),
    ]
    assert events.index("payment.succeeded") < events.index("payment.refunded")
    assert await saga.stock(sku) == 5


async def test_an_order_worth_nothing_is_confirmed_without_a_payment(saga: Saga) -> None:
    customer, sku = uuid4(), await saga.add_product(price="0.00", stock=5)
    await saga.put_in_cart(customer, sku)

    order_id = (await saga.place(customer, sku, "1111", price="0.00")).json()["id"]
    order = await saga.wait_for_status(customer, order_id, "CONFIRMED")

    async def cart_is_empty() -> bool:
        return await saga.cart_skus(customer) == []

    await eventually(cart_is_empty, seconds=WAIT_SECONDS, interval=0.2)
    assert [(a, b) for a, b, _ in history_of(order)] == [
        (None, "PENDING"),
        ("PENDING", "STOCK_RESERVED"),
        ("STOCK_RESERVED", "CONFIRMED"),
    ]
    assert order["total"] == "0.00"
    assert await saga.stock(sku) == 3
    assert await saga.payment(customer, order_id) is None


async def test_an_order_for_more_than_the_stock_is_cancelled_and_nothing_moves(
    saga: Saga,
) -> None:
    customer, sku = uuid4(), await saga.add_product(stock=1)
    order_id = (await saga.place(customer, sku, "1111", quantity=2)).json()["id"]

    order = await saga.wait_for_status(customer, order_id, "CANCELLED")

    assert order["cancel_reason"] == "insufficient_stock"
    assert await saga.stock(sku) == 1
    assert await saga.payment(customer, order_id) is None


async def test_a_price_that_changed_since_the_customer_saw_it_cancels_the_order(
    saga: Saga,
) -> None:
    customer, sku = uuid4(), await saga.add_product(price="10.00", stock=5)
    order_id = (await saga.place(customer, sku, "1111", price="9.99")).json()["id"]

    order = await saga.wait_for_status(customer, order_id, "CANCELLED")

    assert order["cancel_reason"] == "price_changed"
    assert await saga.stock(sku) == 5


async def test_the_same_idempotency_key_buys_once(saga: Saga) -> None:
    customer, sku = uuid4(), await saga.add_product(stock=5)
    key = f"e2e-{uuid4().hex}"

    first = await saga.place(customer, sku, "1111", key=key)
    second = await saga.place(customer, sku, "1111", key=key)
    await saga.wait_for_status(customer, first.json()["id"], "CONFIRMED")

    assert second.json() == first.json()
    assert second.headers["idempotent-replay"] == "true"
    assert await saga.stock(sku) == 3


async def test_twenty_customers_fighting_for_the_last_unit_produce_one_confirmed_order(
    saga: Saga,
) -> None:
    sku = await saga.add_product(stock=1)
    customers = [uuid4() for _ in range(20)]

    placed = await asyncio.gather(
        *(saga.place(customer, sku, "1111", quantity=1) for customer in customers)
    )
    ids = [response.json()["id"] for response in placed]

    async def all_decided() -> bool:
        orders = [
            await saga.order(customer, order_id)
            for customer, order_id in zip(customers, ids, strict=True)
        ]
        return all(order["status"] in {"CONFIRMED", "CANCELLED"} for order in orders)

    await eventually(all_decided, seconds=WAIT_SECONDS, interval=0.3)
    orders = [
        await saga.order(customer, order_id)
        for customer, order_id in zip(customers, ids, strict=True)
    ]
    assert [order["status"] for order in orders].count("CONFIRMED") == 1
    assert {o["cancel_reason"] for o in orders if o["status"] == "CANCELLED"} == {
        "insufficient_stock"
    }
    assert await saga.stock(sku) == 0
