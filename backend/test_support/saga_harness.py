import asyncio
import contextlib
import dataclasses
import json
from collections.abc import AsyncIterator, Callable, Coroutine, Iterable
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
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
from kafka_support import KafkaBroker
from orders.main import create_orders_app
from payments.main import create_payments_app
from redis_support import PASSWORD, RedisServer

BACKEND = Path(__file__).resolve().parents[1]
SAGA_TIMEOUT_SECONDS = 8.0
LATE_APPROVAL_SECONDS = 12.0
TOPICS = ["orders.events", "inventory.events", "payments.events", "catalog.events"]
CART_TTL = 3600
WAIT_SECONDS = 90
WORKER_NAMES = ("catalog", "orders", "payments", "cart", "events")

type WorkerFactory = Callable[[asyncio.Event], Coroutine[Any, Any, None]]


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
    workers: "Workers"
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

    async def count(self, engine: AsyncEngine, statement: str, **parameters: Any) -> int:
        async with engine.connect() as connection:
            return int((await connection.execute(text(statement), parameters)).scalar_one())

    async def unpublished_orders_events(self) -> int:
        return await self.count(
            self.orders_engine, "SELECT count(*) FROM outbox WHERE published_at IS NULL"
        )

    async def payment_rows(self, order_id: str) -> int:
        return await self.count(
            self.payments_engine,
            "SELECT count(*) FROM payments WHERE order_id = :id",
            id=UUID(order_id),
        )

    async def history_rows(self, order_id: str, to_status: str) -> int:
        return await self.count(
            self.orders_engine,
            "SELECT count(*) FROM order_status_history"
            " WHERE order_id = :id AND to_status = :status",
            id=UUID(order_id),
            status=to_status,
        )

    def count_events(self, correlation_id: str, event_type: str) -> int:
        return len([e for e in self.events_of(correlation_id) if e["event_type"] == event_type])

    def events_of(self, correlation_id: str) -> list[dict[str, Any]]:
        return [event for event in self.events if event["correlation_id"] == correlation_id]

    async def wait_for_events(self, correlation_id: str, wanted: set[str]) -> list[str]:
        def seen() -> bool:
            return wanted <= {event["event_type"] for event in self.events_of(correlation_id)}

        await eventually(seen, seconds=WAIT_SECONDS, interval=0.2)
        return [event["event_type"] for event in self.events_of(correlation_id)]


async def collect_events(
    kafka: KafkaBroker, sink: list[dict[str, Any]], stop: asyncio.Event
) -> None:
    group = f"e2e-reader-{uuid4().hex}"
    while not stop.is_set():
        reader = AIOKafkaConsumer(
            *TOPICS,
            bootstrap_servers=kafka.bootstrap,
            group_id=group,
            auto_offset_reset="earliest",
        )
        try:
            await reader.start()
            while not stop.is_set():
                for records in (await reader.getmany(timeout_ms=300)).values():
                    for record in records:
                        event = json.loads(record.value)
                        event["topic"] = record.topic
                        sink.append(event)
        except Exception:
            await asyncio.sleep(0.5)
        finally:
            with contextlib.suppress(Exception):
                await reader.stop()


class Workers:
    def __init__(self, factories: dict[str, WorkerFactory]) -> None:
        self._factories = factories
        self._running: dict[str, tuple[asyncio.Task[None], asyncio.Event]] = {}

    def start(self, name: str) -> None:
        assert name not in self._running, f"{name} is already running"
        stop = asyncio.Event()
        self._running[name] = (asyncio.create_task(self._factories[name](stop)), stop)

    def is_running(self, name: str) -> bool:
        return name in self._running

    async def stop(self, name: str) -> None:
        task, stop = self._running.pop(name)
        stop.set()
        try:
            await asyncio.wait_for(task, timeout=60)
        except (TimeoutError, Exception):
            task.cancel()
            with contextlib.suppress(BaseException):
                await task

    async def stop_all(self) -> None:
        for name in list(self._running):
            await self.stop(name)


@asynccontextmanager
async def running_saga(
    infrastructure: Infrastructure,
    start: Iterable[str] = WORKER_NAMES,
    saga_timeout_seconds: float = SAGA_TIMEOUT_SECONDS,
) -> AsyncIterator[Saga]:
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
    catalog_settings = dataclasses.replace(
        CatalogSettings.from_env(WORKER_ENVIRON), database_url=make_url(infrastructure.catalog_url)
    )
    factories: dict[str, WorkerFactory] = {
        "catalog": lambda stop: catalog_worker.run_worker(
            catalog_worker.WorkerSettings(catalog_settings, kafka_settings), stop
        ),
        "orders": lambda stop: orders_worker.run_worker(
            orders_worker.WorkerSettings(
                make_url(infrastructure.orders_url),
                kafka_settings,
                saga_timeout_seconds=saga_timeout_seconds,
                sweep_interval_seconds=0.3,
            ),
            stop,
        ),
        "payments": lambda stop: payments_worker.run_worker(
            payments_worker.WorkerSettings(
                make_url(infrastructure.payments_url),
                kafka_settings,
                late_approval_delay_seconds=LATE_APPROVAL_SECONDS,
                settle_interval_seconds=0.3,
            ),
            stop,
        ),
        "cart": lambda stop: run_cart_worker(
            CartWorkerSettings(
                redis=RedisSettings(
                    host="127.0.0.1", port=infrastructure.redis.port, password=PASSWORD
                ),
                kafka=kafka_settings,
                ttl_seconds=CART_TTL,
            ),
            stop,
        ),
        "events": lambda stop: collect_events(kafka, events, stop),
    }
    workers = Workers(factories)
    for name in start:
        workers.start(name)
    async with (
        http_client(orders_app) as orders_client,
        http_client(payments_app) as payments_client,
    ):
        try:
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
                workers,
                events,
            )
        finally:
            await workers.stop_all()
    await redis.aclose()
    for engine in (catalog_engine, orders_engine, payments_engine):
        await engine.dispose()


def history_of(order: dict[str, Any]) -> list[tuple[str | None, str, str | None]]:
    return [(h["from_status"], h["to_status"], h["reason"]) for h in order["history"]]
