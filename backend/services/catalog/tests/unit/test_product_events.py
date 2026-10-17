from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from catalog_testing.csv_import import csv_text, row
from catalog_testing.imports import ImportsHarness
from catalog_testing.support import SteppingClock, seeded_store

from catalog.application.errors import PreconditionFailedError
from catalog.application.images import ImageService
from catalog.application.ports import ImageRenditions
from catalog.application.products import ProductService
from catalog.domain.errors import ValidationFailedError
from catalog.domain.preconditions import VersionPrecondition
from catalog.infra.memory import InMemoryStore, InMemoryUnitOfWork
from catalog.infra.memory_imports import OutboxEntry
from ecommerce_contracts import (
    CATALOG_TOPIC,
    PRODUCT_DELETED,
    PRODUCT_UPDATED,
    ProductDeletedV1,
    ProductUpdatedV1,
)
from ecommerce_storage import InMemoryObjectStorage

ANY = VersionPrecondition(any_version=True)
STALE = VersionPrecondition(versions=frozenset({9}))
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 32
SKU = "RS-001"
CORRELATION = UUID(int=42)


class StubProcessor:
    def render(self, data: bytes) -> ImageRenditions:
        return ImageRenditions(thumbnail=b"thumb", full=b"full")


def catalog_events(store: InMemoryStore) -> list[OutboxEntry]:
    return [entry for entry in store.import_data.outbox if entry.topic == CATALOG_TOPIC]


@pytest.fixture
def store() -> InMemoryStore:
    return seeded_store()


@pytest.fixture
def clock() -> SteppingClock:
    return SteppingClock()


@pytest.fixture
def products(store: InMemoryStore, clock: SteppingClock) -> ProductService:
    return ProductService(lambda: InMemoryUnitOfWork(store), clock, lambda: CORRELATION)


@pytest.fixture
def images(store: InMemoryStore, clock: SteppingClock) -> ImageService:
    return ImageService(
        lambda: InMemoryUnitOfWork(store),
        StubProcessor(),
        InMemoryObjectStorage("http://media.test"),
        clock,
        lambda: UUID(int=7),
        correlation_id=lambda: CORRELATION,
    )


async def create(products: ProductService, price: str = "10.00") -> None:
    await products.create(SKU, "Running Shoes", None, None, Decimal(price), 4, None)


async def test_creating_a_product_publishes_an_update_keyed_by_sku(
    products: ProductService, store: InMemoryStore, clock: SteppingClock
) -> None:
    await create(products)

    [event] = catalog_events(store)
    assert (event.key, event.event_type, event.correlation_id) == (
        SKU,
        PRODUCT_UPDATED,
        CORRELATION,
    )
    assert event.payload == ProductUpdatedV1(
        sku=SKU,
        name="Running Shoes",
        price=Decimal("10.00"),
        stock=4,
        image_key=None,
        version=1,
        occurred_at=clock.now,
    )


async def test_replacing_a_product_publishes_the_new_values_and_version(
    products: ProductService, store: InMemoryStore
) -> None:
    await create(products)

    await products.replace(SKU, "Trail Shoes", None, None, Decimal("12.50"), 2, None, ANY)

    payload = catalog_events(store)[-1].payload
    assert isinstance(payload, ProductUpdatedV1)
    assert (payload.name, payload.price, payload.stock, payload.version) == (
        "Trail Shoes",
        Decimal("12.50"),
        2,
        2,
    )
    assert [entry.event_type for entry in catalog_events(store)] == [PRODUCT_UPDATED] * 2


async def test_deleting_a_product_publishes_a_deletion_with_the_new_version(
    products: ProductService, store: InMemoryStore, clock: SteppingClock
) -> None:
    await create(products)

    await products.delete(SKU, ANY)

    last = catalog_events(store)[-1]
    assert (last.key, last.event_type) == (SKU, PRODUCT_DELETED)
    assert last.payload == ProductDeletedV1(sku=SKU, version=2, occurred_at=clock.now)


async def test_a_stale_precondition_publishes_nothing(
    products: ProductService, store: InMemoryStore
) -> None:
    await create(products)

    with pytest.raises(PreconditionFailedError):
        await products.replace(SKU, "x", None, None, Decimal("1.00"), 1, None, STALE)
    with pytest.raises(PreconditionFailedError):
        await products.delete(SKU, STALE)

    assert len(catalog_events(store)) == 1


async def test_a_rejected_write_publishes_nothing(
    products: ProductService, store: InMemoryStore
) -> None:
    with pytest.raises(ValidationFailedError):
        await products.create(SKU, "Shoes", None, uuid4(), Decimal("1.00"), 1, None)

    assert catalog_events(store) == []


async def test_the_correlation_defaults_to_one_per_request(
    store: InMemoryStore, clock: SteppingClock
) -> None:
    service = ProductService(lambda: InMemoryUnitOfWork(store), clock)

    await create(service)

    assert isinstance(catalog_events(store)[0].correlation_id, UUID)


async def test_setting_and_removing_an_image_publish_updates_with_the_image_key(
    products: ProductService, images: ImageService, store: InMemoryStore
) -> None:
    await create(products)

    await images.replace(SKU, JPEG, ANY)
    await images.remove(SKU, ANY)

    with_image, without_image = (entry.payload for entry in catalog_events(store)[1:])
    assert isinstance(with_image, ProductUpdatedV1)
    assert isinstance(without_image, ProductUpdatedV1)
    assert (with_image.image_key, with_image.version) == (f"products/{SKU}/{UUID(int=7)}", 2)
    assert (without_image.image_key, without_image.version) == (None, 3)


async def test_a_failed_image_write_publishes_nothing(
    products: ProductService, images: ImageService, store: InMemoryStore
) -> None:
    await create(products)

    with pytest.raises(PreconditionFailedError):
        await images.replace(SKU, JPEG, STALE)

    assert len(catalog_events(store)) == 1


def seed_events(harness: ImportsHarness) -> list[OutboxEntry]:
    return [item for item in harness.events if item.topic == CATALOG_TOPIC]


async def import_rows(harness: ImportsHarness, *rows: list[str]) -> UUID:
    record = await harness.validated(csv_text(*rows).encode())
    await harness.service.confirm(record.id, uuid4())
    await harness.jobs.process(record.id)
    return record.id


async def test_an_import_publishes_one_update_per_created_updated_or_restored_product() -> None:
    harness = ImportsHarness()
    await import_rows(harness, row(sku="A-1"), row(sku="B-1"), row(sku="C-1"), row(sku="D-1"))
    retired = harness.store.products["D-1"]
    retired.deleted_at = harness.clock()
    retired.version += 1
    before = len(seed_events(harness))

    import_id = await import_rows(
        harness,
        row(sku="A-1"),
        row(sku="B-1", price="7.00"),
        row(sku="C-1", stock="99"),
        row(sku="D-1"),
        row(sku="E-1"),
    )

    new = seed_events(harness)[before:]
    assert sorted(entry.key for entry in new) == ["B-1", "C-1", "D-1", "E-1"]
    assert {entry.event_type for entry in new} == {PRODUCT_UPDATED}
    assert {entry.correlation_id for entry in new} == {import_id}
    versions = {
        entry.key: entry.payload.version
        for entry in new
        if isinstance(entry.payload, ProductUpdatedV1)
    }
    assert versions == {"B-1": 2, "C-1": 2, "D-1": 3, "E-1": 1}


async def test_an_import_of_unchanged_data_publishes_nothing() -> None:
    harness = ImportsHarness()
    await import_rows(harness, row(sku="A-1"), row(sku="B-1"))
    before = len(seed_events(harness))

    await import_rows(harness, row(sku="A-1"), row(sku="B-1"))

    assert len(seed_events(harness)) == before


async def test_an_import_event_keeps_the_image_key_of_the_product() -> None:
    harness = ImportsHarness()
    await import_rows(harness, row(sku="A-1"))
    harness.store.products["A-1"].image_key = "products/A-1/abc"

    await import_rows(harness, row(sku="A-1", price="9.00"))

    payload = seed_events(harness)[-1].payload
    assert isinstance(payload, ProductUpdatedV1)
    assert (payload.image_key, payload.price) == ("products/A-1/abc", Decimal("9.00"))
