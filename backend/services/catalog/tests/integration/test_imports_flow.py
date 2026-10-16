import asyncio
import csv
import io
from collections.abc import AsyncIterator, Callable
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from botocore.exceptions import ClientError
from catalog_testing import images
from catalog_testing.imports import SAMPLE
from catalog_testing.support import bearer, build_test_app, http_client, valid_product
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from catalog.application.import_jobs import ImportJobs
from catalog.infra.database import create_engine, create_session_factory
from catalog.infra.models import OUTBOX
from catalog.infra.unit_of_work import SqlAlchemyUnitOfWork
from catalog.worker import build_consumer
from ecommerce_auth import Role
from ecommerce_auth.testing import StubTokenIssuer
from ecommerce_contracts import IMPORTS_TOPIC
from ecommerce_messaging import (
    InMemoryBroker,
    KafkaPublisher,
    KafkaSettings,
    KafkaSource,
    OutboxRelay,
    RetryPolicy,
)
from ecommerce_storage import S3ObjectStorage, build_s3_client
from kafka_support import KafkaBroker
from seaweedfs_support import SeaweedFs

pytestmark = pytest.mark.integration

IMPORTS = "/api/v1/imports"
FAST_RETRY = RetryPolicy(max_attempts=3, base_delay_seconds=0.05, max_delay_seconds=0.2)


class Stack:
    def __init__(
        self,
        engine: AsyncEngine,
        client: httpx.AsyncClient,
        admin: dict[str, str],
        storage: S3ObjectStorage,
        seaweedfs: SeaweedFs,
    ) -> None:
        self.engine = engine
        self.sessions: async_sessionmaker[AsyncSession] = create_session_factory(engine)
        self.client = client
        self.admin = admin
        self.storage = storage
        self.seaweedfs = seaweedfs
        self.jobs = ImportJobs(lambda: SqlAlchemyUnitOfWork(self.sessions), storage)

    async def upload(self, data: bytes = SAMPLE, filename: str = "products.csv") -> httpx.Response:
        body, content_type = images.multipart([("file", filename, data, "text/csv")])
        return await self.client.post(
            IMPORTS, content=body, headers=self.admin | {"Content-Type": content_type}
        )

    async def get(self, import_id: str) -> dict[str, Any]:
        response = await self.client.get(f"{IMPORTS}/{import_id}", headers=self.admin)
        body: dict[str, Any] = response.json()
        return body

    async def confirm(self, import_id: str) -> httpx.Response:
        return await self.client.post(f"{IMPORTS}/{import_id}/confirm", headers=self.admin)

    async def scalar(self, query: str, **params: object) -> Any:
        async with self.sessions() as session:
            return await session.scalar(text(query), params)

    def stored_objects(self) -> list[str]:
        client = build_s3_client(self.seaweedfs.settings)
        listing = client.list_objects_v2(Bucket="imports", Prefix="imports/")
        return sorted(item["Key"] for item in listing.get("Contents", []))

    async def pump(self) -> None:
        broker = InMemoryBroker()
        relay = OutboxRelay(OUTBOX, self.sessions, broker)
        while await relay.drain_once():
            pass
        source = broker.source([IMPORTS_TOPIC])
        consumer = build_consumer(self.jobs, source, broker, self.sessions, retry=FAST_RETRY)
        while (message := await source.poll(0)) is not None:
            await consumer.handle(message)


@pytest.fixture
async def stack(
    empty_database_url: str,
    alembic_runner: Callable[[str, str, str], None],
    seaweedfs: SeaweedFs,
    issuer: StubTokenIssuer,
) -> AsyncIterator[Stack]:
    alembic_runner(empty_database_url, "upgrade", "head")
    engine = create_engine(empty_database_url)
    sessions = create_session_factory(engine)
    storage = S3ObjectStorage(
        build_s3_client(seaweedfs.settings), seaweedfs.imports_bucket, seaweedfs.endpoint
    )
    app = build_test_app(issuer, lambda: SqlAlchemyUnitOfWork(sessions), imports_storage=storage)
    async with http_client(app) as client:
        yield Stack(engine, client, bearer(issuer, Role.ADMIN), storage, seaweedfs)
    await engine.dispose()


async def test_the_sample_file_goes_from_upload_to_catalog_with_an_explicit_confirmation(
    stack: Stack,
) -> None:
    created = await stack.upload()
    import_id = created.json()["id"]
    assert created.status_code == 202
    assert created.json()["status"] == "uploaded"
    assert f"imports/{import_id}/source.csv" in stack.stored_objects()

    await stack.pump()
    validated = await stack.get(import_id)

    assert validated["status"] == "validated"
    summary = validated["summary"]
    assert (
        summary["rows_read"],
        summary["blank_rows"],
        summary["error_rows"],
        summary["warning_count"],
        summary["importable_rows"],
        summary["to_create"],
    ) == (97, 2, 4, 3, 88, 88)
    assert [(item["row"], item["severity"]) for item in validated["problems"]] == [
        (7, "error"),
        (16, "error"),
        (25, "error"),
        (41, "error"),
        (2, "warning"),
        (4, "warning"),
        (56, "warning"),
    ]
    assert await stack.scalar("SELECT count(*) FROM products") == 0

    confirmed = await stack.confirm(import_id)
    assert confirmed.status_code == 202
    assert confirmed.json()["status"] == "queued"
    assert await stack.scalar("SELECT count(*) FROM products") == 0

    await stack.pump()
    finished = await stack.get(import_id)

    assert finished["status"] == "completed"
    assert finished["progress"] == {
        "processed_rows": 88,
        "created_rows": 88,
        "updated_rows": 0,
        "restored_rows": 0,
        "unchanged_rows": 0,
    }
    assert await stack.scalar("SELECT count(*) FROM products") == 88
    assert await stack.scalar("SELECT count(*) FROM products WHERE version <> 1") == 0


async def test_hostile_names_are_stored_literally_and_the_table_survives(stack: Stack) -> None:
    import_id = (await stack.upload()).json()["id"]
    await stack.pump()
    await stack.confirm(import_id)
    await stack.pump()

    sql = await stack.client.get("/api/v1/products/SQL-001")
    script = await stack.client.get("/api/v1/products/XS-001")

    assert sql.json()["name"] == "Robert'); DROP TABLE products;--"
    assert script.json()["name"] == "<script>alert('xss')</script>"
    assert await stack.scalar("SELECT count(*) FROM products") == 88
    assert await stack.scalar("SELECT to_regclass('public.products') IS NOT NULL") is True


async def test_the_imported_products_are_searchable_and_use_the_last_duplicate(
    stack: Stack,
) -> None:
    import_id = (await stack.upload()).json()["id"]
    await stack.pump()
    await stack.confirm(import_id)
    await stack.pump()

    shoes = (await stack.client.get("/api/v1/products/RS-001")).json()
    speaker = (await stack.client.get("/api/v1/products/BS-021")).json()
    found = (await stack.client.get("/api/v1/products", params={"q": "yoga block"})).json()

    assert (shoes["price"], shoes["stock"]) == ("94.99", 120)
    assert (speaker["price"], speaker["stock"]) == ("59.99", 110)
    assert next(item["sku"] for item in found["items"]) == "YB-016"


async def test_uploading_the_same_file_twice_does_not_duplicate_the_work(stack: Stack) -> None:
    first = await stack.upload()
    objects_after_first = stack.stored_objects()
    second = await stack.upload(filename="renamed.csv")

    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert stack.stored_objects() == objects_after_first
    assert await stack.scalar("SELECT count(*) FROM imports") == 1
    assert await stack.scalar("SELECT count(*) FROM outbox") == 1


async def test_the_problems_can_be_downloaded_as_a_csv(stack: Stack) -> None:
    import_id = (await stack.upload()).json()["id"]
    await stack.pump()

    response = await stack.client.get(f"{IMPORTS}/{import_id}/problems.csv", headers=stack.admin)

    assert response.status_code == 200
    rows = list(csv.reader(io.StringIO(response.content.decode().removeprefix("﻿"))))
    assert rows[0] == ["severity", "row", "column", "value", "code", "reason"]
    assert [item[1] for item in rows[1:]] == ["2", "4", "7", "16", "25", "41", "56"]


async def test_a_second_import_updates_changes_and_leaves_the_rest_alone(stack: Stack) -> None:
    first = (await stack.upload()).json()["id"]
    await stack.pump()
    await stack.confirm(first)
    await stack.pump()
    untouched = await stack.scalar("SELECT updated_at FROM products WHERE sku = 'CB-010'")
    changed = SAMPLE.replace(
        b"Running Shoes,RS-001,Updated lightweight shoes", b"Running Shoes,RS-001,New text"
    )
    changed += b"\r\nBrand New,NEW-001,desc,Books,5.00,5,0.1"

    second = (await stack.upload(changed)).json()["id"]
    await stack.pump()
    preview = (await stack.get(second))["summary"]
    await stack.confirm(second)
    await stack.pump()
    result = await stack.get(second)

    assert (preview["to_create"], preview["to_update"], preview["unchanged"]) == (1, 1, 87)
    assert result["progress"] == {
        "processed_rows": 89,
        "created_rows": 1,
        "updated_rows": 1,
        "restored_rows": 0,
        "unchanged_rows": 87,
    }
    assert await stack.scalar("SELECT version FROM products WHERE sku = 'RS-001'") == 2
    assert await stack.scalar("SELECT version FROM products WHERE sku = 'CB-010'") == 1
    assert await stack.scalar("SELECT updated_at FROM products WHERE sku = 'CB-010'") == untouched
    assert await stack.scalar("SELECT count(*) FROM products") == 89


async def test_a_product_deleted_after_the_first_import_is_restored_by_the_next_one(
    stack: Stack,
) -> None:
    first = (await stack.upload()).json()["id"]
    await stack.pump()
    await stack.confirm(first)
    await stack.pump()
    deleted = await stack.client.delete(
        "/api/v1/products/CB-010", headers=stack.admin | {"If-Match": "*"}
    )
    blocked = await stack.client.post(
        "/api/v1/products", json=valid_product(sku="CB-010"), headers=stack.admin
    )
    again = SAMPLE + b"\r\nBrand New,NEW-001,desc,Books,5.00,5,0.1"

    second = (await stack.upload(again)).json()["id"]
    await stack.pump()
    preview = (await stack.get(second))["summary"]
    await stack.confirm(second)
    await stack.pump()
    restored = await stack.client.get("/api/v1/products/CB-010")

    assert deleted.status_code == 204
    assert blocked.status_code == 409
    assert (preview["to_restore"], preview["to_create"], preview["unchanged"]) == (1, 1, 87)
    assert restored.status_code == 200
    assert restored.json()["version"] == 3
    assert (await stack.get(second))["progress"]["restored_rows"] == 1


async def test_a_file_changed_behind_our_back_fails_the_import_and_lands_in_the_dead_letter_topic(
    stack: Stack,
) -> None:
    created = (await stack.upload()).json()
    key = f"imports/{created['id']}/source.csv"
    await stack.storage.put(key, SAMPLE + b"\r\nTampered,TAMP-1,x,Books,1.00,1,0.1", "text/csv")
    broker = InMemoryBroker()
    relay = OutboxRelay(OUTBOX, stack.sessions, broker)
    await relay.drain_once()
    source = broker.source([IMPORTS_TOPIC])
    consumer = build_consumer(stack.jobs, source, broker, stack.sessions, retry=FAST_RETRY)
    message = await source.poll(0)
    assert message is not None

    await consumer.handle(message)

    failed = await stack.get(created["id"])
    assert failed["status"] == "failed"
    assert "ImportFileChangedError" in failed["failure_reason"]
    [dead] = broker.messages(IMPORTS_TOPIC + ".dlq")
    assert dead.headers["x-error-type"] == b"ImportFileChangedError"
    assert (await stack.confirm(created["id"])).status_code == 409


async def test_creating_the_missing_category_and_validating_again_replaces_the_old_results(
    stack: Stack,
) -> None:
    file = (
        b"name,sku,description,category,price,stock,weight_kg\r\n"
        b"Rake,G-1,,Gardening,12.00,5,\r\n"
        b"Spade,G-2,,Gardening,15.00,5,\r\n"
        b"Boots,F-1,,Footwear,40.00,5,\r\n"
    )
    created = (await stack.upload(file)).json()
    import_id = created["id"]
    await stack.pump()
    before = await stack.get(import_id)
    assert before["status"] == "validated"
    assert before["summary"]["importable_rows"] == 1
    assert before["summary"]["unknown_categories"][0]["value"] == "Gardening"
    assert {item["code"] for item in before["problems"]} == {"unknown_category"}
    assert await stack.scalar("SELECT count(*) FROM import_problems") == 2

    created_category = await stack.client.post(
        "/api/v1/categories", json={"name": "Gardening"}, headers=stack.admin
    )
    assert created_category.status_code == 201

    revalidated = await stack.client.post(f"{IMPORTS}/{import_id}/revalidate", headers=stack.admin)

    assert revalidated.status_code == 202
    assert revalidated.json()["status"] == "uploaded"
    pending = await stack.get(import_id)
    assert pending["summary"] is None
    assert pending["problems"] == []
    assert await stack.scalar("SELECT count(*) FROM import_problems") == 0
    assert await stack.scalar("SELECT category_snapshot IS NULL FROM imports") is True

    await stack.pump()
    after = await stack.get(import_id)

    assert after["status"] == "validated"
    assert after["summary"]["unknown_categories"] == []
    assert after["summary"]["error_rows"] == 0
    assert after["summary"]["importable_rows"] == 3
    assert after["problems"] == []
    assert await stack.scalar("SELECT count(*) FROM import_problems") == 0
    snapshot = await stack.scalar("SELECT category_snapshot FROM imports")
    assert "Gardening" in {item["name"] for item in snapshot}
    assert after["links"]["confirm"] is not None
    assert await stack.scalar("SELECT count(*) FROM products") == 0


async def test_a_rejected_file_is_never_confirmable(stack: Stack) -> None:
    created = (await stack.upload(b"colour,size\r\nred,1\r\n")).json()
    await stack.pump()

    rejected = await stack.get(created["id"])
    confirm = await stack.confirm(created["id"])

    assert rejected["status"] == "rejected"
    assert confirm.status_code == 409
    assert await stack.scalar("SELECT count(*) FROM products") == 0


async def test_the_uploaded_object_is_private(stack: Stack) -> None:
    created = (await stack.upload()).json()
    key = f"imports/{created['id']}/source.csv"

    async with httpx.AsyncClient() as anonymous:
        response = await anonymous.get(f"{stack.seaweedfs.endpoint}/imports/{key}")

    assert response.status_code == 403
    assert key in stack.stored_objects()


async def test_the_database_is_the_only_place_that_lists_the_import(stack: Stack) -> None:
    created = (await stack.upload()).json()

    with pytest.raises(ClientError):
        build_s3_client(stack.seaweedfs.settings).head_object(
            Bucket="media", Key=f"imports/{created['id']}/source.csv"
        )
    assert UUID(created["id"])


class Worker:
    def __init__(self, stack: Stack, kafka: KafkaBroker) -> None:
        settings = KafkaSettings(kafka.bootstrap, "test-worker", publish_timeout_seconds=10)
        self.publisher = KafkaPublisher(settings)
        self.source = KafkaSource(settings, [IMPORTS_TOPIC], f"test-{uuid4().hex}")
        self.relay = OutboxRelay(OUTBOX, stack.sessions, self.publisher, poll_interval_seconds=0.1)
        self.consumer = build_consumer(
            stack.jobs,
            self.source,
            self.publisher,
            stack.sessions,
            f"group-{uuid4().hex}",
            FAST_RETRY,
        )
        self.stop = asyncio.Event()
        self.tasks: list[asyncio.Task[None]] = []

    def start(self) -> None:
        self.tasks = [
            asyncio.create_task(self.relay.run(self.stop)),
            asyncio.create_task(self.consumer.run(self.stop)),
        ]

    async def shutdown(self) -> None:
        self.stop.set()
        await asyncio.gather(*self.tasks)
        await self.source.close()
        await self.publisher.close()


async def wait_for_status(stack: Stack, import_id: str, wanted: str) -> dict[str, Any]:
    async with asyncio.timeout(90):
        while True:
            body = await stack.get(import_id)
            if body["status"] == wanted:
                return body
            await asyncio.sleep(0.2)


async def test_the_worker_imports_the_sample_file_through_kafka(
    stack: Stack, kafka: KafkaBroker
) -> None:
    worker = Worker(stack, kafka)
    worker.start()
    try:
        import_id = (await stack.upload()).json()["id"]
        validated = await wait_for_status(stack, import_id, "validated")
        assert await stack.scalar("SELECT count(*) FROM products") == 0
        await stack.confirm(import_id)
        completed = await wait_for_status(stack, import_id, "completed")
    finally:
        await worker.shutdown()

    assert validated["summary"]["importable_rows"] == 88
    assert completed["progress"]["created_rows"] == 88
    assert await stack.scalar("SELECT count(*) FROM products") == 88
    assert await stack.scalar("SELECT count(*) FROM outbox WHERE published_at IS NULL") == 0


async def test_uploads_survive_kafka_being_down_and_are_validated_when_it_returns(
    stack: Stack, stoppable_kafka: KafkaBroker
) -> None:
    stoppable_kafka.stop()
    created = await stack.upload()
    assert created.status_code == 202
    worker = Worker(stack, stoppable_kafka)
    worker.start()
    try:
        await asyncio.sleep(1.5)
        assert (await stack.get(created.json()["id"]))["status"] == "uploaded"
        stoppable_kafka.start()
        validated = await wait_for_status(stack, created.json()["id"], "validated")
    finally:
        await worker.shutdown()

    assert validated["summary"]["importable_rows"] == 88
