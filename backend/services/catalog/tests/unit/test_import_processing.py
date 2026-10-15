from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from catalog_testing.csv_import import csv_text, row
from catalog_testing.imports import SAMPLE, ImportsHarness

from catalog.application.import_jobs import ImportFileChangedError
from catalog.domain.imports import ImportRecord, ImportStatus, Progress
from catalog.infra.memory import StoredProduct
from catalog.infra.memory_imports import InMemoryImportRepository


async def confirmed(harness: ImportsHarness, data: bytes = SAMPLE) -> ImportRecord:
    record = await harness.validated(data)
    return await harness.service.confirm(record.id, uuid4())


async def processed(harness: ImportsHarness, data: bytes = SAMPLE) -> ImportRecord:
    record = await confirmed(harness, data)
    await harness.jobs.process(record.id)
    return await harness.service.get(record.id)


def seed(
    harness: ImportsHarness,
    sku: str,
    price: str = "89.99",
    stock: int = 150,
    deleted: bool = False,
    image_key: str | None = None,
) -> StoredProduct:
    footwear = next(
        item.id for item in harness.store.categories.values() if item.name == "Footwear"
    )
    now = harness.clock()
    stored = StoredProduct(
        id=uuid4(),
        sku=sku,
        name="Running Shoes",
        description="Lightweight running shoes",
        category_id=footwear,
        price=Decimal(price),
        stock=stock,
        weight_kg=Decimal("0.350"),
        version=3,
        created_at=now,
        updated_at=now,
        deleted_at=now if deleted else None,
        image_key=image_key,
    )
    harness.store.products[sku] = stored
    return stored


async def test_the_sample_file_is_imported_into_the_catalog() -> None:
    harness = ImportsHarness()

    record = await processed(harness)

    assert record.status is ImportStatus.COMPLETED
    assert record.finished_at is not None
    assert record.progress == Progress(88, 88, 0, 0, 0)
    assert len(harness.store.products) == 88
    assert {"YM-015", "DL-007", "HD-099", "WS-001"}.isdisjoint(harness.store.products)


async def test_the_winning_rows_carry_the_expected_data() -> None:
    harness = ImportsHarness()
    await processed(harness)
    products = harness.store.products

    assert products["RS-001"].price == Decimal("94.99")
    assert products["RS-001"].stock == 120
    assert products["BS-021"].price == Decimal("59.99")
    assert products["WM-042"].price == Decimal("29.99")
    assert products["GK-088"].weight_kg is None
    assert products["GC-025"].category_id is None
    assert products["XS-001"].name == "<script>alert('xss')</script>"
    assert products["SQL-001"].name == "Robert'); DROP TABLE products;--"
    assert all(item.version == 1 for item in products.values())


async def test_nothing_is_written_until_the_import_is_confirmed_and_processed() -> None:
    harness = ImportsHarness()
    record = await confirmed(harness)

    assert harness.store.products == {}
    assert record.status is ImportStatus.QUEUED


async def test_an_import_that_was_never_confirmed_is_not_processed() -> None:
    harness = ImportsHarness()
    record = await harness.validated()

    await harness.jobs.process(record.id)

    assert harness.store.products == {}
    assert (await harness.service.get(record.id)).status is ImportStatus.VALIDATED


async def test_processing_an_unknown_import_does_nothing() -> None:
    await ImportsHarness().jobs.process(uuid4())


async def test_a_redelivered_request_after_completion_changes_nothing() -> None:
    harness = ImportsHarness()
    record = await processed(harness)
    before = {sku: item.version for sku, item in harness.store.products.items()}

    await harness.jobs.process(record.id)

    assert {sku: item.version for sku, item in harness.store.products.items()} == before
    assert (await harness.service.get(record.id)).progress == record.progress


async def test_existing_products_are_updated_and_their_version_bumped() -> None:
    harness = ImportsHarness()
    seed(harness, "RS-001", price="1.00")
    harness.clock.advance(5)
    data = csv_text(row(sku="RS-001", price="94.99")).encode()

    record = await processed(harness, data)

    stored = harness.store.products["RS-001"]
    assert (stored.price, stored.version) == (Decimal("94.99"), 4)
    assert stored.updated_at > stored.created_at
    assert record.progress == Progress(1, 0, 1, 0, 0)


async def test_rows_identical_to_the_catalog_are_left_untouched() -> None:
    harness = ImportsHarness()
    seeded = seed(harness, "RS-001")
    harness.clock.advance(60)
    updated_at = seeded.updated_at

    record = await processed(harness, csv_text(row(sku="RS-001")).encode())

    stored = harness.store.products["RS-001"]
    assert (stored.version, stored.updated_at) == (3, updated_at)
    assert record.progress == Progress(1, 0, 0, 0, 1)


async def test_a_soft_deleted_product_is_restored_with_a_new_version() -> None:
    harness = ImportsHarness()
    seed(harness, "RS-001", deleted=True)

    record = await processed(harness, csv_text(row(sku="RS-001")).encode())

    stored = harness.store.products["RS-001"]
    assert stored.deleted_at is None
    assert stored.version == 4
    assert record.progress == Progress(1, 0, 0, 1, 0)


async def test_the_image_of_an_existing_product_survives_an_import() -> None:
    harness = ImportsHarness()
    seed(harness, "RS-001", price="1.00", image_key="products/RS-001/abc")

    await processed(harness, csv_text(row(sku="RS-001", price="5.00")).encode())

    assert harness.store.products["RS-001"].image_key == "products/RS-001/abc"


async def test_importing_the_same_data_twice_changes_nothing_the_second_time() -> None:
    harness = ImportsHarness()
    await processed(harness)
    extra = SAMPLE + b"\r\nExtra Item,EX-001,desc,Books,5.00,5,0.1"

    second = await processed(harness, extra)

    assert second.progress == Progress(89, 1, 0, 0, 88)
    assert all(item.version == 1 for sku, item in harness.store.products.items() if sku != "EX-001")


@pytest.mark.parametrize("batch_size", [1, 7, 88, 1000])
async def test_the_batch_size_does_not_change_the_result(batch_size: int) -> None:
    harness = ImportsHarness(batch_size=batch_size)

    record = await processed(harness)

    assert record.progress == Progress(88, 88, 0, 0, 0)
    assert len(harness.store.products) == 88


async def test_progress_is_recorded_after_every_batch() -> None:
    harness = ImportsHarness(batch_size=30)
    record = await confirmed(harness)
    snapshots: list[int] = []
    repository = InMemoryImportRepository
    recorded = repository.record_progress

    async def spy(self, import_id, progress, now):  # type: ignore[no-untyped-def]
        snapshots.append(progress.processed_rows)
        await recorded(self, import_id, progress, now)

    repository.record_progress = spy  # type: ignore[method-assign]
    try:
        await harness.jobs.process(record.id)
    finally:
        repository.record_progress = recorded  # type: ignore[method-assign]

    assert snapshots == [0, 30, 60, 88]


async def test_a_new_run_after_a_crash_completes_the_import() -> None:
    harness = ImportsHarness(batch_size=10)
    record = await confirmed(harness)
    await harness.jobs.process(record.id)
    harness.store.import_data.records[record.id] = replace(
        await harness.service.get(record.id), status=ImportStatus.PROCESSING
    )
    for sku in list(harness.store.products)[:30]:
        del harness.store.products[sku]

    await harness.jobs.process(record.id)

    final = await harness.service.get(record.id)
    assert final.status is ImportStatus.COMPLETED
    assert len(harness.store.products) == 88
    assert final.progress.processed_rows == 88


async def test_a_file_that_changed_after_validation_is_not_imported() -> None:
    harness = ImportsHarness()
    record = await confirmed(harness)
    await harness.storage.put(record.object_key, SAMPLE + b"\r\nnew,row", "text/csv")

    with pytest.raises(ImportFileChangedError):
        await harness.jobs.process(record.id)

    assert harness.store.products == {}
    assert (await harness.service.get(record.id)).status is ImportStatus.PROCESSING


async def test_the_categories_known_at_validation_decide_what_is_imported() -> None:
    harness = ImportsHarness()
    data = csv_text(row(sku="A-1", category="Brand New"), row(sku="A-2")).encode()
    record = await confirmed(harness, data)
    harness.store.seed_categories(("Brand New", "brand-new"))

    await harness.jobs.process(record.id)

    assert set(harness.store.products) == {"A-2"}


async def test_failing_a_processing_import_marks_it_failed_without_undoing_the_batches() -> None:
    harness = ImportsHarness(batch_size=40)
    record = await confirmed(harness)
    await harness.jobs.process(record.id)
    harness.store.import_data.records[record.id] = replace(
        await harness.service.get(record.id), status=ImportStatus.PROCESSING
    )

    await harness.jobs.fail(record.id, "Boom: bad")

    failed = await harness.service.get(record.id)
    assert failed.status is ImportStatus.FAILED
    assert failed.failure_reason == "Boom: bad"
    assert len(harness.store.products) == 88


async def test_timestamps_follow_the_clock() -> None:
    harness = ImportsHarness()
    record = await confirmed(harness)
    harness.clock.advance(5)

    await harness.jobs.process(record.id)

    finished = await harness.service.get(record.id)
    assert finished.finished_at is not None
    assert finished.finished_at - record.created_at >= timedelta(minutes=5)
