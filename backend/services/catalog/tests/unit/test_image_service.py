import asyncio
import logging
import threading
import time
from collections.abc import Awaitable, Callable
from decimal import Decimal
from uuid import UUID

import pytest
from catalog_testing.support import SteppingClock, seeded_store

from catalog.application.errors import (
    InvalidUploadError,
    PreconditionFailedError,
    ProductImageNotFoundError,
    ProductNotFoundError,
    UnsupportedMediaError,
)
from catalog.application.images import ImageService
from catalog.application.ports import ImageRenditions
from catalog.application.products import ProductService
from catalog.domain.image import IMMUTABLE_CACHE_CONTROL
from catalog.domain.preconditions import VersionPrecondition
from catalog.infra.memory import InMemoryStore, InMemoryUnitOfWork
from ecommerce_storage import InMemoryObjectStorage, ObjectStorageError, full_key, thumbnail_key

ANY = VersionPrecondition(any_version=True)
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 32
SKU = "RS-001"


class StubProcessor:
    def __init__(self) -> None:
        self.calls = 0
        self.active = 0
        self.peak = 0
        self._lock = threading.Lock()
        self.delay = 0.0

    def render(self, data: bytes) -> ImageRenditions:
        with self._lock:
            self.calls += 1
            self.active += 1
            self.peak = max(self.peak, self.active)
        time.sleep(self.delay)
        with self._lock:
            self.active -= 1
        return ImageRenditions(thumbnail=b"thumb", full=b"full")


class ScriptedStorage(InMemoryObjectStorage):
    def __init__(self) -> None:
        super().__init__("http://media.test")
        self.fail_put_number: int | None = None
        self.fail_deletes = False
        self.after_put: Callable[[], Awaitable[None]] | None = None
        self.puts = 0

    async def put(
        self, key: str, data: bytes, content_type: str, cache_control: str | None = None
    ) -> None:
        self.puts += 1
        if self.fail_put_number == self.puts:
            raise ObjectStorageError("storage is down")
        await super().put(key, data, content_type, cache_control)
        if self.after_put is not None:
            await self.after_put()

    async def delete(self, key: str) -> None:
        if self.fail_deletes:
            raise ObjectStorageError("storage is down")
        await super().delete(key)


class FailingCommitUnitOfWork(InMemoryUnitOfWork):
    async def commit(self) -> None:
        raise RuntimeError("database went away")


class Fixture:
    def __init__(self) -> None:
        self.store: InMemoryStore = seeded_store()
        self.clock = SteppingClock()
        self.storage = ScriptedStorage()
        self.processor = StubProcessor()
        self.fail_commit = False
        self.identifiers = iter(UUID(int=number) for number in range(1, 1000))
        self.service = ImageService(
            self.unit_of_work,
            self.processor,
            self.storage,
            self.clock,
            lambda: next(self.identifiers),
        )

    def unit_of_work(self) -> InMemoryUnitOfWork:
        return (
            FailingCommitUnitOfWork(self.store)
            if self.fail_commit
            else InMemoryUnitOfWork(self.store)
        )

    async def create(self, sku: str = SKU) -> None:
        products = ProductService(lambda: InMemoryUnitOfWork(self.store), self.clock)
        await products.create(sku, "Running Shoes", None, None, Decimal("10.00"), 1, None)

    def stored(self, sku: str = SKU) -> tuple[str | None, int]:
        item = self.store.products[sku]
        return item.image_key, item.version


@pytest.fixture
async def fixture() -> Fixture:
    prepared = Fixture()
    await prepared.create()
    return prepared


def uuid_key(number: int, sku: str = SKU) -> str:
    return f"products/{sku}/{UUID(int=number)}"


async def test_replacing_the_image_stores_both_renditions_and_bumps_the_version(
    fixture: Fixture,
) -> None:
    product = await fixture.service.replace(SKU, JPEG, ANY)

    key = uuid_key(1)
    assert product.image_key == key
    assert product.version == 2
    assert fixture.storage.keys() == sorted([thumbnail_key(key), full_key(key)])
    thumbnail = fixture.storage.get(thumbnail_key(key))
    assert thumbnail is not None
    assert (thumbnail.data, thumbnail.content_type) == (b"thumb", "image/webp")
    assert thumbnail.cache_control == IMMUTABLE_CACHE_CONTROL
    full = fixture.storage.get(full_key(key))
    assert full is not None
    assert full.cache_control == IMMUTABLE_CACHE_CONTROL
    assert fixture.stored() == (key, 2)


async def test_replacing_again_changes_the_key_and_removes_the_old_objects_afterwards(
    fixture: Fixture,
) -> None:
    await fixture.service.replace(SKU, JPEG, ANY)

    product = await fixture.service.replace(SKU, JPEG, ANY)

    new_key = uuid_key(2)
    assert product.image_key == new_key
    assert product.version == 3
    assert fixture.storage.keys() == sorted([thumbnail_key(new_key), full_key(new_key)])


async def test_the_sku_is_normalised_in_the_key(fixture: Fixture) -> None:
    product = await fixture.service.replace(" rs-001 ", JPEG, ANY)

    assert product.image_key is not None
    assert product.image_key.startswith("products/RS-001/")


async def test_a_stale_precondition_stores_nothing_and_skips_processing(fixture: Fixture) -> None:
    with pytest.raises(PreconditionFailedError):
        await fixture.service.replace(SKU, JPEG, VersionPrecondition.parse('"7"'))

    assert fixture.storage.keys() == []
    assert fixture.processor.calls == 0
    assert fixture.stored() == (None, 1)


async def test_an_unknown_sku_is_not_found(fixture: Fixture) -> None:
    with pytest.raises(ProductNotFoundError):
        await fixture.service.replace("NOPE-1", JPEG, ANY)

    assert fixture.processor.calls == 0


@pytest.mark.parametrize(
    "data", [b"plain text pretending to be a jpg", b"GIF89a....", b"<html></html>"]
)
async def test_content_that_is_not_a_supported_image_is_refused(
    fixture: Fixture, data: bytes
) -> None:
    with pytest.raises(UnsupportedMediaError):
        await fixture.service.replace(SKU, data, ANY)

    assert fixture.processor.calls == 0
    assert fixture.storage.keys() == []


async def test_an_empty_file_is_refused(fixture: Fixture) -> None:
    with pytest.raises(InvalidUploadError):
        await fixture.service.replace(SKU, b"", ANY)


async def test_a_failure_uploading_the_first_rendition_leaves_nothing_behind(
    fixture: Fixture,
) -> None:
    fixture.storage.fail_put_number = 1

    with pytest.raises(ObjectStorageError):
        await fixture.service.replace(SKU, JPEG, ANY)

    assert fixture.storage.keys() == []
    assert fixture.stored() == (None, 1)


async def test_a_failure_uploading_the_second_rendition_removes_the_first(
    fixture: Fixture,
) -> None:
    fixture.storage.fail_put_number = 2

    with pytest.raises(ObjectStorageError):
        await fixture.service.replace(SKU, JPEG, ANY)

    assert fixture.storage.keys() == []
    assert fixture.stored() == (None, 1)


async def test_a_failed_commit_deletes_the_new_objects_and_keeps_the_old_image(
    fixture: Fixture,
) -> None:
    await fixture.service.replace(SKU, JPEG, ANY)
    old_keys = fixture.storage.keys()
    fixture.fail_commit = True

    with pytest.raises(RuntimeError, match="database went away"):
        await fixture.service.replace(SKU, JPEG, ANY)

    assert fixture.storage.keys() == old_keys
    assert fixture.stored() == (uuid_key(1), 2)


async def test_a_conflict_that_appears_while_uploading_is_caught_before_the_commit(
    fixture: Fixture,
) -> None:
    async def someone_else_edits_the_product() -> None:
        fixture.storage.after_put = None
        fixture.store.products[SKU].version += 1

    fixture.storage.after_put = someone_else_edits_the_product

    with pytest.raises(PreconditionFailedError):
        await fixture.service.replace(SKU, JPEG, VersionPrecondition.parse('"1"'))

    assert fixture.storage.keys() == []
    assert fixture.stored() == (None, 2)


async def test_a_cancelled_request_cleans_up_what_it_uploaded(fixture: Fixture) -> None:
    async def cancelled() -> None:
        raise asyncio.CancelledError

    fixture.storage.after_put = cancelled

    with pytest.raises(asyncio.CancelledError):
        await fixture.service.replace(SKU, JPEG, ANY)

    assert fixture.storage.keys() == []


async def test_a_failure_deleting_the_old_objects_does_not_fail_the_replacement(
    fixture: Fixture, caplog: pytest.LogCaptureFixture
) -> None:
    await fixture.service.replace(SKU, JPEG, ANY)
    fixture.storage.fail_deletes = True

    with caplog.at_level(logging.WARNING, logger="catalog.application.images"):
        product = await fixture.service.replace(SKU, JPEG, ANY)

    assert product.image_key == uuid_key(2)
    assert fixture.stored() == (uuid_key(2), 3)
    assert {thumbnail_key(uuid_key(1)), full_key(uuid_key(1))} <= set(fixture.storage.keys())
    orphans = [record for record in caplog.records if record.message.startswith("image cleanup")]
    assert {record.key for record in orphans} == {  # type: ignore[attr-defined]
        thumbnail_key(uuid_key(1)),
        full_key(uuid_key(1)),
    }


async def test_removing_the_image_clears_the_key_deletes_the_objects_and_bumps_the_version(
    fixture: Fixture,
) -> None:
    await fixture.service.replace(SKU, JPEG, ANY)

    product = await fixture.service.remove(SKU, ANY)

    assert product.image_key is None
    assert product.version == 3
    assert fixture.storage.keys() == []
    assert fixture.stored() == (None, 3)


async def test_removing_a_missing_image_is_not_found_and_changes_nothing(
    fixture: Fixture,
) -> None:
    with pytest.raises(ProductImageNotFoundError):
        await fixture.service.remove(SKU, ANY)

    assert fixture.stored() == (None, 1)


async def test_removing_with_a_stale_version_is_refused(fixture: Fixture) -> None:
    await fixture.service.replace(SKU, JPEG, ANY)

    with pytest.raises(PreconditionFailedError):
        await fixture.service.remove(SKU, VersionPrecondition.parse('"1"'))

    assert len(fixture.storage.keys()) == 2


async def test_removal_succeeds_even_if_the_objects_cannot_be_deleted(fixture: Fixture) -> None:
    await fixture.service.replace(SKU, JPEG, ANY)
    fixture.storage.fail_deletes = True

    product = await fixture.service.remove(SKU, ANY)

    assert product.image_key is None
    assert len(fixture.storage.keys()) == 2


async def test_only_two_images_are_rendered_at_the_same_time() -> None:
    fixture = Fixture()
    for number in range(6):
        await fixture.create(f"P-{number}")
    fixture.processor.delay = 0.05

    await asyncio.gather(
        *(fixture.service.replace(f"P-{number}", JPEG, ANY) for number in range(6))
    )

    assert fixture.processor.calls == 6
    assert fixture.processor.peak == 2
