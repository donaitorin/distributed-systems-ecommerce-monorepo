import csv
import io
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from catalog_testing.csv_import import csv_text, row
from catalog_testing.imports import SAMPLE, ImportsHarness, stream

from catalog.application.cursors import InvalidCursorError
from catalog.application.errors import (
    DuplicateImportError,
    ImportNotConfirmableError,
    ImportNotFoundError,
    ImportTooLargeError,
    InvalidUploadError,
)
from catalog.application.imports import (
    decode_problem_cursor,
    encode_problem_cursor,
    neutralize_formula,
)
from catalog.domain.imports import ImportStatus, clean_filename, import_object_key
from ecommerce_contracts import (
    IMPORT_REQUESTED,
    IMPORT_VALIDATION_REQUESTED,
    IMPORTS_TOPIC,
)


async def test_uploading_stores_the_file_registers_the_import_and_queues_the_validation() -> None:
    harness = ImportsHarness()

    result = await harness.upload(SAMPLE, filename="catalog.csv", user="admin-7")

    record = result.record
    assert result.created
    assert (record.status, record.filename, record.created_by) == (
        ImportStatus.UPLOADED,
        "catalog.csv",
        "admin-7",
    )
    assert record.size_bytes == len(SAMPLE)
    assert len(record.sha256) == 64
    assert record.object_key == import_object_key(record.id)
    stored = harness.storage.get(record.object_key)
    assert stored is not None
    assert (stored.data, stored.content_type) == (SAMPLE, "text/csv")
    [event] = harness.events
    assert (event.topic, event.key, event.event_type) == (
        IMPORTS_TOPIC,
        str(record.id),
        IMPORT_VALIDATION_REQUESTED,
    )
    assert event.payload.import_id == record.id  # type: ignore[attr-defined]
    assert event.payload.sha256 == record.sha256  # type: ignore[attr-defined]


async def test_the_same_file_uploaded_twice_returns_the_existing_import_and_keeps_one_object() -> (
    None
):
    harness = ImportsHarness()
    first = await harness.upload()

    second = await harness.upload(filename="renamed.csv")

    assert not second.created
    assert second.record.id == first.record.id
    assert harness.storage.keys() == [first.record.object_key]
    assert len(harness.events) == 1


async def test_a_different_file_is_a_new_import() -> None:
    harness = ImportsHarness()
    first = await harness.upload(csv_text(row(sku="A-1")).encode())

    second = await harness.upload(csv_text(row(sku="A-2")).encode())

    assert second.created
    assert second.record.id != first.record.id
    assert len(harness.storage.keys()) == 2


async def test_a_failed_import_does_not_block_uploading_the_same_file_again() -> None:
    harness = ImportsHarness()
    first = await harness.upload()
    await harness.jobs.fail(first.record.id, "boom")

    second = await harness.upload()

    assert second.created
    assert second.record.id != first.record.id


async def test_a_file_over_the_limit_is_refused_and_leaves_nothing_behind() -> None:
    harness = ImportsHarness(max_bytes=1000)

    with pytest.raises(ImportTooLargeError) as raised:
        await harness.upload(b"x" * 5000)

    assert raised.value.limit_bytes == 1000
    assert harness.storage.keys() == []
    assert harness.events == []
    assert harness.store.import_data.records == {}


async def test_a_file_exactly_at_the_limit_is_accepted() -> None:
    harness = ImportsHarness(max_bytes=len(SAMPLE))

    assert (await harness.upload()).created


async def test_a_stream_that_fails_leaves_nothing_behind() -> None:
    harness = ImportsHarness()

    async def broken() -> AsyncIterator[bytes]:
        yield b"name,sku"
        raise InvalidUploadError("missing_file", "the multipart field 'file' is required")

    with pytest.raises(InvalidUploadError):
        await harness.service.upload(broken(), "admin", uuid4())

    assert harness.storage.keys() == []
    assert harness.store.import_data.records == {}


async def test_a_registration_failure_removes_the_uploaded_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = ImportsHarness()

    async def failing(*args: object, **kwargs: object) -> None:
        raise RuntimeError("database went away")

    monkeypatch.setattr("catalog.infra.memory_imports.InMemoryEventOutbox.add", failing)

    with pytest.raises(RuntimeError):
        await harness.upload()

    assert harness.storage.keys() == []
    assert harness.store.import_data.records == {}


async def test_losing_the_race_for_the_same_file_returns_the_winner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = ImportsHarness()
    winner = await harness.upload()
    original = type(harness.service)._find_by_hash
    calls = {"count": 0}

    async def blind_first_time(self: object, digest: str):  # type: ignore[no-untyped-def]
        calls["count"] += 1
        return None if calls["count"] == 1 else await original(self, digest)  # type: ignore[arg-type]

    monkeypatch.setattr(type(harness.service), "_find_by_hash", blind_first_time)

    loser = await harness.upload()

    assert not loser.created
    assert loser.record.id == winner.record.id
    assert harness.storage.keys() == [winner.record.object_key]


async def test_a_duplicate_error_without_a_winner_is_not_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = ImportsHarness()

    async def always_duplicate(*args: object, **kwargs: object) -> None:
        raise DuplicateImportError("x")

    monkeypatch.setattr(
        "catalog.infra.memory_imports.InMemoryImportRepository.add", always_duplicate
    )

    with pytest.raises(DuplicateImportError):
        await harness.upload()

    assert harness.storage.keys() == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("products.csv", "products.csv"),
        ("C:\\Users\\me\\products.csv", "products.csv"),
        ("/tmp/../etc/products.csv", "products.csv"),
        ("bad\x00name\n.csv", "badname.csv"),
        ("", "products.csv"),
        (None, "products.csv"),
        ("   ", "products.csv"),
        ("x" * 400 + ".csv", ("x" * 400 + ".csv")[:255]),
    ],
)
def test_file_names_are_reduced_to_a_safe_display_name(raw: str | None, expected: str) -> None:
    assert clean_filename(raw) == expected


async def test_getting_an_unknown_import_is_not_found() -> None:
    with pytest.raises(ImportNotFoundError):
        await ImportsHarness().service.get(uuid4())


async def test_the_preview_lists_errors_before_warnings_up_to_the_limit() -> None:
    harness = ImportsHarness()
    record = await harness.validated()

    _, preview = await harness.service.preview(record.id, 5)

    assert [item.severity for item in preview] == ["error"] * 4 + ["warning"]
    assert len(preview) == 5


async def test_problems_are_paged_with_an_opaque_cursor() -> None:
    harness = ImportsHarness()
    record = await harness.validated()

    first = await harness.service.problems(record.id, None, None, 3)
    second = await harness.service.problems(record.id, None, first.next_cursor, 3)
    third = await harness.service.problems(record.id, None, second.next_cursor, 3)

    assert [item.row for item in first.items] == [2, 4, 7]
    assert [item.row for item in second.items] == [16, 25, 41]
    assert [item.row for item in third.items] == [56]
    assert third.next_cursor is None
    assert first.next_cursor is not None


async def test_problems_can_be_filtered_by_severity() -> None:
    harness = ImportsHarness()
    record = await harness.validated()

    errors = await harness.service.problems(record.id, "error", None, 100)
    warnings = await harness.service.problems(record.id, "warning", None, 100)

    assert [item.row for item in errors.items] == [7, 16, 25, 41]
    assert [item.row for item in warnings.items] == [2, 4, 56]


async def test_problems_of_an_unknown_import_are_not_found() -> None:
    with pytest.raises(ImportNotFoundError):
        await ImportsHarness().service.problems(uuid4(), None, None, 10)


@pytest.mark.parametrize("raw", ["", "not-base64!!", "YWJj", "LTE", "////"])
def test_a_malformed_problem_cursor_is_rejected(raw: str) -> None:
    with pytest.raises(InvalidCursorError):
        decode_problem_cursor(raw)


def test_a_problem_cursor_round_trips() -> None:
    assert decode_problem_cursor(encode_problem_cursor(12345)) == 12345


async def collect(harness: ImportsHarness, import_id) -> str:  # type: ignore[no-untyped-def]
    chunks = [chunk async for chunk in harness.service.problems_csv(import_id)]
    return b"".join(chunks).decode()


async def test_the_problems_csv_has_a_bom_a_header_and_one_line_per_problem() -> None:
    harness = ImportsHarness()
    record = await harness.validated()

    text = await collect(harness, record.id)

    assert text.startswith("\ufeffseverity,row,column,value,code,reason\r\n")
    rows = list(csv.reader(io.StringIO(text.removeprefix("\ufeff"))))
    assert len(rows) == 1 + 7
    assert rows[1][:5] == ["warning", "2", "sku", "RS-001", "superseded"]
    assert rows[3] == [
        "error",
        "7",
        "price",
        "free",
        "not_a_number",
        "price must be a plain number such as 29.99",
    ]


async def test_the_problems_csv_streams_in_batches_for_large_reports() -> None:
    harness = ImportsHarness()
    content = csv_text(*(row(sku=f"S-{number}", name="") for number in range(1200))).encode()
    record = await harness.validated(content)

    chunks = [chunk async for chunk in harness.service.problems_csv(record.id)]

    assert len(chunks) == 1 + 3
    text = b"".join(chunks).decode().removeprefix("\ufeff")
    assert len(list(csv.reader(io.StringIO(text)))) == 1 + 1200


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("=SUM(A1:A9)", "'=SUM(A1:A9)"),
        ("+cmd|' /C calc'!A0", "'+cmd|' /C calc'!A0"),
        ("@SUM(1)", "'@SUM(1)"),
        ("-2+3", "'-2+3"),
        ("\tTabbed", "'\tTabbed"),
        ("\rReturn", "'\rReturn"),
        ("-5", "-5"),
        ("+7.25", "+7.25"),
        ("free", "free"),
        ("", ""),
        (None, ""),
        ("12-3", "12-3"),
    ],
)
def test_cells_that_a_spreadsheet_would_run_as_formulas_are_neutralized(
    value: str | None, expected: str
) -> None:
    assert neutralize_formula(value) == expected


async def test_the_csv_neutralizes_hostile_values_from_the_uploaded_file() -> None:
    harness = ImportsHarness()
    content = csv_text(row(name='=HYPERLINK("http://evil")', price="@bad")).encode()
    record = await harness.validated(content)

    text = await collect(harness, record.id)

    assert "'@bad" in text


async def test_confirming_a_validated_import_queues_it_and_publishes_the_request() -> None:
    harness = ImportsHarness()
    record = await harness.validated()
    correlation = uuid4()

    confirmed = await harness.service.confirm(record.id, correlation)

    assert confirmed.status is ImportStatus.QUEUED
    assert confirmed.confirmed_at is not None
    [request] = [item for item in harness.events if item.event_type == IMPORT_REQUESTED]
    assert (request.topic, request.key, request.correlation_id) == (
        IMPORTS_TOPIC,
        str(record.id),
        correlation,
    )
    assert request.payload.object_key == record.object_key  # type: ignore[attr-defined]
    assert request.payload.sha256 == record.sha256  # type: ignore[attr-defined]


async def test_confirming_twice_does_not_publish_twice() -> None:
    harness = ImportsHarness()
    record = await harness.validated()
    await harness.service.confirm(record.id, uuid4())

    again = await harness.service.confirm(record.id, uuid4())

    assert again.status is ImportStatus.QUEUED
    assert len(harness.event_payloads(IMPORT_REQUESTED)) == 1


async def test_nothing_is_written_to_the_catalog_without_confirmation() -> None:
    harness = ImportsHarness()

    await harness.validated()

    assert harness.store.products == {}


@pytest.mark.parametrize(
    ("status", "fragment"),
    [
        (ImportStatus.UPLOADED, "not been validated"),
        (ImportStatus.VALIDATING, "still being validated"),
        (ImportStatus.REJECTED, "rejected as a whole"),
        (ImportStatus.FAILED, "import failed"),
    ],
)
async def test_an_import_that_is_not_validated_cannot_be_confirmed(
    status: ImportStatus, fragment: str
) -> None:
    harness = ImportsHarness()
    result = await harness.upload()
    from dataclasses import replace

    harness.store.import_data.records[result.record.id] = replace(result.record, status=status)

    with pytest.raises(ImportNotConfirmableError) as raised:
        await harness.service.confirm(result.record.id, uuid4())

    assert fragment in raised.value.reason
    assert raised.value.status == status.value
    assert harness.event_payloads(IMPORT_REQUESTED) == []


async def test_an_import_without_valid_rows_cannot_be_confirmed() -> None:
    harness = ImportsHarness()
    record = await harness.validated(csv_text(row(name="")).encode())

    with pytest.raises(ImportNotConfirmableError) as raised:
        await harness.service.confirm(record.id, uuid4())

    assert "no valid rows" in raised.value.reason


async def test_confirming_an_unknown_import_is_not_found() -> None:
    with pytest.raises(ImportNotFoundError):
        await ImportsHarness().service.confirm(uuid4(), uuid4())


async def test_the_streamed_upload_helper_yields_the_whole_file() -> None:
    assert b"".join([chunk async for chunk in stream(SAMPLE, 100)]) == SAMPLE
