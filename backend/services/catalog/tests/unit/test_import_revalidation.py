from dataclasses import replace
from uuid import uuid4

import pytest
from catalog_testing.csv_import import csv_text, row
from catalog_testing.imports import ImportsHarness

from catalog.application.errors import ImportNotFoundError, ImportNotRevalidatableError
from catalog.domain.imports import ImportStatus
from ecommerce_contracts import IMPORT_VALIDATION_REQUESTED, IMPORTS_TOPIC

UNKNOWN_CATEGORY_FILE = csv_text(
    row(sku="G-1", category="Gardening"),
    row(sku="G-2", category="Gardening"),
    row(sku="F-1", category="Footwear"),
    row(sku="E-1", category="Electornics"),
).encode()


async def uploaded_with_unknown_categories(harness: ImportsHarness):  # type: ignore[no-untyped-def]
    record = await harness.validated(UNKNOWN_CATEGORY_FILE)
    assert record.summary is not None
    assert {item.value for item in record.summary.unknown_categories} == {
        "Gardening",
        "Electornics",
    }
    return record


async def test_validating_again_after_creating_the_category_replaces_every_previous_result() -> (
    None
):
    harness = ImportsHarness()
    first = await uploaded_with_unknown_categories(harness)
    assert first.summary is not None
    assert first.summary.error_rows == 3
    old_codes = {
        item.code for item in (await harness.service.problems(first.id, None, None, 50)).items
    }
    assert "unknown_category" in old_codes
    harness.store.seed_categories(("Gardening", "gardening"))

    queued = await harness.service.revalidate(first.id, uuid4())
    assert queued.status is ImportStatus.UPLOADED
    assert queued.summary is None
    assert queued.validated_at is None
    assert (await harness.service.problems(first.id, None, None, 50)).items == []
    async with harness.unit_of_work() as uow:
        assert await uow.imports.category_snapshot(first.id) == []

    await harness.jobs.validate(first.id)
    again = await harness.service.get(first.id)

    assert again.status is ImportStatus.VALIDATED
    assert again.summary is not None
    assert [item.value for item in again.summary.unknown_categories] == ["Electornics"]
    assert again.summary.error_rows == 1
    assert again.summary.importable_rows == 3
    remaining = (await harness.service.problems(first.id, None, None, 50)).items
    assert [item.row for item in remaining] == [5]
    async with harness.unit_of_work() as uow:
        snapshot = await uow.imports.category_snapshot(first.id)
    assert "Gardening" in {item.name for item in snapshot}
    assert len(snapshot) == 19


async def test_revalidating_publishes_one_validation_request_with_the_file_reference() -> None:
    harness = ImportsHarness()
    record = await uploaded_with_unknown_categories(harness)
    correlation = uuid4()

    await harness.service.revalidate(record.id, correlation)

    requests = [item for item in harness.events if item.event_type == IMPORT_VALIDATION_REQUESTED]
    assert len(requests) == 2
    latest = requests[-1]
    assert (latest.topic, latest.key, latest.correlation_id) == (
        IMPORTS_TOPIC,
        str(record.id),
        correlation,
    )
    assert latest.payload.object_key == record.object_key  # type: ignore[attr-defined]
    assert latest.payload.sha256 == record.sha256  # type: ignore[attr-defined]


async def test_revalidating_twice_while_pending_is_harmless_and_publishes_once() -> None:
    harness = ImportsHarness()
    record = await uploaded_with_unknown_categories(harness)

    first = await harness.service.revalidate(record.id, uuid4())
    second = await harness.service.revalidate(record.id, uuid4())

    assert first.status is second.status is ImportStatus.UPLOADED
    assert len(harness.event_payloads(IMPORT_VALIDATION_REQUESTED)) == 2


async def test_a_validation_in_progress_is_left_alone() -> None:
    harness = ImportsHarness()
    result = await harness.upload()
    harness.store.import_data.records[result.record.id] = replace(
        result.record, status=ImportStatus.VALIDATING
    )

    current = await harness.service.revalidate(result.record.id, uuid4())

    assert current.status is ImportStatus.VALIDATING
    assert len(harness.event_payloads(IMPORT_VALIDATION_REQUESTED)) == 1


async def test_a_rejected_file_can_be_validated_again() -> None:
    harness = ImportsHarness()
    record = await harness.validated(b"colour,size\r\nred,1\r\n")
    assert record.status is ImportStatus.REJECTED
    before = (await harness.service.problems(record.id, None, None, 50)).items
    assert before != []

    await harness.service.revalidate(record.id, uuid4())
    await harness.jobs.validate(record.id)
    again = await harness.service.get(record.id)

    assert again.status is ImportStatus.REJECTED
    after = (await harness.service.problems(record.id, None, None, 50)).items
    assert [item.code for item in after] == [item.code for item in before]
    assert {item.id for item in after}.isdisjoint({item.id for item in before})


@pytest.mark.parametrize(
    ("status", "fragment"),
    [
        (ImportStatus.QUEUED, "already confirmed"),
        (ImportStatus.PROCESSING, "being processed"),
        (ImportStatus.COMPLETED, "import is complete"),
        (ImportStatus.FAILED, "import failed"),
    ],
)
async def test_an_import_past_validation_cannot_be_validated_again(
    status: ImportStatus, fragment: str
) -> None:
    harness = ImportsHarness()
    record = await harness.validated()
    harness.store.import_data.records[record.id] = replace(record, status=status)
    before = len(harness.events)

    with pytest.raises(ImportNotRevalidatableError) as raised:
        await harness.service.revalidate(record.id, uuid4())

    assert fragment in raised.value.reason
    assert raised.value.status == status.value
    assert len(harness.events) == before
    assert (await harness.service.get(record.id)).summary is not None
    assert (await harness.service.problems(record.id, None, None, 50)).items != []


async def test_revalidating_an_unknown_import_is_not_found() -> None:
    with pytest.raises(ImportNotFoundError):
        await ImportsHarness().service.revalidate(uuid4(), uuid4())


async def test_a_confirmed_import_keeps_its_results_when_validation_is_refused() -> None:
    harness = ImportsHarness()
    record = await harness.validated()
    await harness.service.confirm(record.id, uuid4())

    with pytest.raises(ImportNotRevalidatableError):
        await harness.service.revalidate(record.id, uuid4())

    assert (await harness.service.get(record.id)).status is ImportStatus.QUEUED
