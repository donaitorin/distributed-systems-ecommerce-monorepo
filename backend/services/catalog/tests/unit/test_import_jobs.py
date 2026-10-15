from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest
from catalog_testing.csv_import import csv_text, row
from catalog_testing.imports import SAMPLE, ImportsHarness

from catalog.application.import_jobs import ImportFileChangedError
from catalog.domain.csv_import import ImportableRow
from catalog.domain.imports import ExistingProduct, ImportStatus, classify
from catalog.domain.product import NewProduct, ProductData


def product_data(price: str = "10.00", stock: int = 1) -> ProductData:
    return ProductData("Shoes", None, None, Decimal(price), stock, None)


def incoming(sku: str, data: ProductData) -> ImportableRow:
    return ImportableRow(2, NewProduct(sku, data))


def test_rows_are_classified_as_create_update_restore_or_unchanged() -> None:
    rows = [
        incoming("NEW-1", product_data()),
        incoming("SAME-1", product_data()),
        incoming("CHANGED-1", product_data("11.00")),
        incoming("GONE-1", product_data()),
        incoming("GONE-2", product_data("99.00")),
    ]
    existing = {
        "SAME-1": ExistingProduct(False, product_data()),
        "CHANGED-1": ExistingProduct(False, product_data("10.00")),
        "GONE-1": ExistingProduct(True, product_data()),
        "GONE-2": ExistingProduct(True, product_data("10.00")),
    }

    assert classify(rows, existing) == (1, 1, 2, 1)


async def test_validating_the_sample_file_stores_the_expected_report() -> None:
    harness = ImportsHarness()

    record = await harness.validated()

    summary = record.summary
    assert record.status is ImportStatus.VALIDATED
    assert summary is not None
    assert (
        summary.rows_read,
        summary.blank_rows,
        summary.error_rows,
        summary.error_count,
        summary.warning_count,
        summary.superseded_rows,
        summary.duplicate_rows,
        summary.importable_rows,
    ) == (97, 2, 4, 4, 3, 2, 1, 88)
    assert (summary.to_create, summary.to_update, summary.to_restore, summary.unchanged) == (
        88,
        0,
        0,
        0,
    )
    assert not summary.rejected
    assert record.validated_at is not None


async def test_the_stored_problems_match_the_sample_report() -> None:
    harness = ImportsHarness()
    record = await harness.validated()

    page = await harness.service.problems(record.id, None, None, 100)

    assert [(item.row, item.severity, item.code) for item in page.items] == [
        (2, "warning", "superseded"),
        (4, "warning", "price_normalized"),
        (7, "error", "not_a_number"),
        (16, "error", "negative"),
        (25, "error", "required"),
        (41, "error", "required"),
        (56, "warning", "superseded"),
    ]


async def test_the_categories_seen_during_validation_are_remembered() -> None:
    harness = ImportsHarness()
    record = await harness.validated()

    async with harness.unit_of_work() as uow:
        snapshot = await uow.imports.category_snapshot(record.id)

    assert len(snapshot) == 18
    assert "Footwear" in {item.name for item in snapshot}


async def test_unknown_categories_are_summarized_with_suggestions() -> None:
    harness = ImportsHarness()
    content = csv_text(
        row(sku="A-1", category="Electornics"), row(sku="A-2", category="Electornics")
    ).encode()

    record = await harness.validated(content)

    assert record.summary is not None
    [unknown] = record.summary.unknown_categories
    assert (unknown.value, unknown.rows, unknown.suggestion) == ("Electornics", 2, "Electronics")
    assert record.summary.importable_rows == 0


async def test_a_file_that_is_not_a_csv_is_rejected_as_a_whole() -> None:
    harness = ImportsHarness()

    record = await harness.validated(b"\x89PNG\r\n\x1a\n\x00\x00binary")

    assert record.status is ImportStatus.REJECTED
    assert record.summary is not None
    assert record.summary.rejected
    page = await harness.service.problems(record.id, None, None, 10)
    assert [item.code for item in page.items] == ["not_text"]
    assert page.items[0].row is None


async def test_every_document_problem_is_stored_for_a_rejected_file() -> None:
    harness = ImportsHarness()

    record = await harness.validated(b"colour,size\r\nred,10\r\n")

    page = await harness.service.problems(record.id, None, None, 100)
    assert record.status is ImportStatus.REJECTED
    assert sorted(item.code for item in page.items) == [
        "missing_column",
        "missing_column",
        "missing_column",
        "missing_column",
        "unknown_column",
        "unknown_column",
    ]


async def test_an_empty_file_is_rejected() -> None:
    harness = ImportsHarness()

    record = await harness.validated(b"")

    assert record.status is ImportStatus.REJECTED


async def test_the_preview_counts_existing_products_as_updates_restores_and_unchanged() -> None:
    harness = ImportsHarness()
    await _seed_product(harness, "A-1", "Running Shoes", "89.99", 150, "0.350", deleted=False)
    await _seed_product(harness, "A-2", "Running Shoes", "1.00", 5, "0.350", deleted=False)
    await _seed_product(harness, "A-3", "Running Shoes", "89.99", 150, "0.350", deleted=True)
    content = csv_text(row(sku="A-1"), row(sku="A-2"), row(sku="A-3"), row(sku="A-4")).encode()

    record = await harness.validated(content)

    summary = record.summary
    assert summary is not None
    assert (summary.to_create, summary.to_update, summary.to_restore, summary.unchanged) == (
        1,
        1,
        1,
        1,
    )


async def _seed_product(
    harness: ImportsHarness,
    sku: str,
    name: str,
    price: str,
    stock: int,
    weight: str,
    deleted: bool,
) -> None:
    from catalog_testing.csv_import import category_id

    from catalog.infra.memory import StoredProduct

    footwear = next(
        item.id for item in harness.store.categories.values() if item.name == "Footwear"
    )
    assert footwear == category_id("Footwear") or footwear is not None
    now = harness.clock()
    harness.store.products[sku] = StoredProduct(
        id=uuid4(),
        sku=sku,
        name=name,
        description="Lightweight running shoes",
        category_id=footwear,
        price=Decimal(price),
        stock=stock,
        weight_kg=Decimal(weight),
        version=1,
        created_at=now,
        updated_at=now,
        deleted_at=now if deleted else None,
    )


async def test_validation_is_idempotent_when_the_event_is_delivered_again() -> None:
    harness = ImportsHarness()
    record = await harness.validated()

    await harness.jobs.validate(record.id)

    again = await harness.service.get(record.id)
    assert again == record


async def test_validating_an_unknown_import_does_nothing() -> None:
    await ImportsHarness().jobs.validate(uuid4())


async def test_validation_resumes_an_import_left_in_the_validating_state() -> None:
    harness = ImportsHarness()
    result = await harness.upload()
    harness.store.import_data.records[result.record.id] = replace(
        result.record, status=ImportStatus.VALIDATING
    )

    await harness.jobs.validate(result.record.id)

    assert (await harness.service.get(result.record.id)).status is ImportStatus.VALIDATED


async def test_a_file_that_changed_after_the_upload_is_not_trusted() -> None:
    harness = ImportsHarness()
    result = await harness.upload()
    await harness.storage.put(result.record.object_key, SAMPLE + b"\r\nextra,row", "text/csv")

    with pytest.raises(ImportFileChangedError):
        await harness.jobs.validate(result.record.id)

    assert (await harness.service.get(result.record.id)).status is ImportStatus.VALIDATING


async def test_a_result_arriving_after_the_import_failed_is_discarded() -> None:
    harness = ImportsHarness()
    result = await harness.upload()
    original = type(harness.jobs)._with_preview

    async def fail_meanwhile(self, *args):  # type: ignore[no-untyped-def]
        await harness.jobs.fail(result.record.id, "gave up")
        return await original(self, *args)

    type(harness.jobs)._with_preview = fail_meanwhile  # type: ignore[method-assign]
    try:
        await harness.jobs.validate(result.record.id)
    finally:
        type(harness.jobs)._with_preview = original  # type: ignore[method-assign]

    assert (await harness.service.get(result.record.id)).status is ImportStatus.FAILED


async def test_failing_an_import_records_the_reason_and_only_applies_to_open_imports() -> None:
    harness = ImportsHarness()
    result = await harness.upload()

    await harness.jobs.fail(result.record.id, "ValueError: bad")
    failed = await harness.service.get(result.record.id)
    await harness.jobs.fail(result.record.id, "second reason")

    assert failed.status is ImportStatus.FAILED
    assert failed.failure_reason == "ValueError: bad"
    assert failed.finished_at is not None
    assert (await harness.service.get(result.record.id)).failure_reason == "ValueError: bad"


async def test_a_completed_import_cannot_be_failed_afterwards() -> None:
    harness = ImportsHarness()
    result = await harness.upload()
    harness.store.import_data.records[result.record.id] = replace(
        result.record, status=ImportStatus.COMPLETED
    )

    await harness.jobs.fail(result.record.id, "late")

    assert (await harness.service.get(result.record.id)).status is ImportStatus.COMPLETED


async def test_small_batches_give_the_same_preview() -> None:
    small = ImportsHarness(batch_size=7)
    large = ImportsHarness()

    first = await small.validated()
    second = await large.validated()

    assert first.summary == second.summary
