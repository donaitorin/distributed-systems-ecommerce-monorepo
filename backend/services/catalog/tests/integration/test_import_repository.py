import asyncio
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from catalog.application.errors import DuplicateImportError
from catalog.domain.csv_import import ImportableRow, Problem, Severity
from catalog.domain.imports import (
    CategoryRef,
    ImportStatus,
    ImportSummary,
    NewImport,
    Progress,
)
from catalog.domain.product import NewProduct, ProductData
from catalog.infra.database import create_engine, create_session_factory
from catalog.infra.unit_of_work import SqlAlchemyUnitOfWork
from ecommerce_contracts import IMPORTS_TOPIC, ImportRequestedV1

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=5)
type Factory = Callable[[], SqlAlchemyUnitOfWork]


@pytest.fixture
async def factory(
    empty_database_url: str, alembic_runner: Callable[[str, str, str], None]
) -> AsyncIterator[Factory]:
    alembic_runner(empty_database_url, "upgrade", "head")
    engine = create_engine(empty_database_url)
    sessions = create_session_factory(engine)
    yield lambda: SqlAlchemyUnitOfWork(sessions)
    await engine.dispose()


def incoming(
    sku: str, price: str = "10.00", name: str = "Shoes", stock: int = 5, description: str = "desc"
) -> ImportableRow:
    data = ProductData(name, description, None, Decimal(price), stock, Decimal("0.5"))
    return ImportableRow(2, NewProduct(sku, data))


async def upsert(factory: Factory, rows: list[ImportableRow], now: datetime = NOW) -> Progress:
    async with factory() as uow:
        progress = await uow.products.upsert_many(rows, now)
        await uow.commit()
    return progress


async def product(factory: Factory, sku: str) -> dict[str, Any]:
    async with factory() as uow:
        result = await uow._session.execute(
            text(
                "SELECT version, price, name, stock, deleted_at, image_key, updated_at "
                "FROM products WHERE sku = :sku"
            ),
            {"sku": sku},
        )
        return dict(result.mappings().one())


async def scalar(factory: Factory, query: str, **params: object) -> Any:
    async with factory() as uow:
        return await uow._session.scalar(text(query), params)


async def test_new_rows_are_inserted_with_version_one(factory: Factory) -> None:
    progress = await upsert(factory, [incoming("A-1"), incoming("A-2")])

    assert progress == Progress(2, 2, 0, 0, 0)
    stored = await product(factory, "A-1")
    assert (stored["version"], stored["price"], stored["deleted_at"]) == (1, Decimal("10.00"), None)


async def test_changed_rows_are_updated_and_their_version_bumped(factory: Factory) -> None:
    await upsert(factory, [incoming("A-1")])

    progress = await upsert(factory, [incoming("A-1", price="12.50", name="Better")], LATER)

    assert progress == Progress(1, 0, 1, 0, 0)
    stored = await product(factory, "A-1")
    assert (stored["version"], stored["price"], stored["name"]) == (2, Decimal("12.50"), "Better")
    assert stored["updated_at"] == LATER


async def test_identical_rows_do_not_touch_the_product(factory: Factory) -> None:
    await upsert(factory, [incoming("A-1")])

    progress = await upsert(factory, [incoming("A-1")], LATER)

    assert progress == Progress(1, 0, 0, 0, 1)
    stored = await product(factory, "A-1")
    assert (stored["version"], stored["updated_at"]) == (1, NOW)


async def test_a_soft_deleted_product_is_restored_and_its_version_bumped(factory: Factory) -> None:
    await upsert(factory, [incoming("A-1")])
    async with factory() as uow:
        await uow.products.soft_delete("A-1", NOW)
        await uow.commit()
    deleted = await product(factory, "A-1")

    progress = await upsert(factory, [incoming("A-1")], LATER)

    restored = await product(factory, "A-1")
    assert deleted["deleted_at"] is not None
    assert progress == Progress(1, 0, 0, 1, 0)
    assert restored["deleted_at"] is None
    assert restored["version"] == deleted["version"] + 1


async def test_the_image_of_a_product_is_never_touched_by_an_upsert(factory: Factory) -> None:
    await upsert(factory, [incoming("A-1")])
    async with factory() as uow:
        await uow.products.set_image("A-1", "products/A-1/abc", NOW)
        await uow.commit()

    await upsert(factory, [incoming("A-1", price="99.00")], LATER)

    assert (await product(factory, "A-1"))["image_key"] == "products/A-1/abc"


async def test_a_mixed_batch_gets_the_right_counts_and_effects(factory: Factory) -> None:
    await upsert(factory, [incoming("SAME"), incoming("CHANGED"), incoming("GONE")])
    async with factory() as uow:
        await uow.products.soft_delete("GONE", NOW)
        await uow.commit()

    progress = await upsert(
        factory,
        [incoming("SAME"), incoming("CHANGED", stock=9), incoming("GONE"), incoming("FRESH")],
        LATER,
    )

    assert progress == Progress(4, 1, 1, 1, 1)
    assert (await product(factory, "SAME"))["version"] == 1
    assert (await product(factory, "CHANGED"))["stock"] == 9
    assert (await product(factory, "FRESH"))["version"] == 1


async def test_a_thousand_rows_go_in_one_statement(factory: Factory) -> None:
    rows = [incoming(f"B-{number:04d}", name=f"Product {number}") for number in range(1000)]

    progress = await upsert(factory, rows)

    assert progress == Progress(1000, 1000, 0, 0, 0)
    assert await scalar(factory, "SELECT count(*) FROM products") == 1000


async def test_names_that_look_like_sql_are_stored_literally_and_the_table_survives(
    factory: Factory,
) -> None:
    hostile = "Robert'); DROP TABLE products;--"

    await upsert(factory, [incoming("SQL-001", name=hostile)])

    assert (await product(factory, "SQL-001"))["name"] == hostile
    assert await scalar(factory, "SELECT count(*) FROM products") == 1


async def test_the_search_vector_follows_an_upsert(factory: Factory) -> None:
    await upsert(factory, [incoming("A-1", name="Plain Mug")])
    await upsert(factory, [incoming("A-1", name="Trail Sandals")], LATER)

    found = await scalar(
        factory,
        "SELECT count(*) FROM products WHERE search_vector @@ websearch_to_tsquery('english', :q)",
        q="sandals",
    )
    assert found == 1


def new_import(digest: str = "a" * 64, identifier: UUID | None = None) -> NewImport:
    import_id = identifier or uuid4()
    key = f"imports/{import_id}/source.csv"
    return NewImport(import_id, "products.csv", key, digest, 10, "admin")


async def test_an_import_is_stored_and_found_by_its_hash(factory: Factory) -> None:
    async with factory() as uow:
        added = await uow.imports.add(new_import(), NOW)
        await uow.commit()

    async with factory() as uow:
        by_hash = await uow.imports.find_by_hash("a" * 64)
        by_id = await uow.imports.get(added.id)

    assert by_hash == by_id == added
    assert added.status is ImportStatus.UPLOADED


async def test_the_same_hash_cannot_be_registered_twice_unless_the_first_failed(
    factory: Factory,
) -> None:
    async with factory() as uow:
        first = await uow.imports.add(new_import(), NOW)
        await uow.commit()
    async with factory() as uow:
        with pytest.raises(DuplicateImportError):
            await uow.imports.add(new_import(), NOW)
    async with factory() as uow:
        await uow.imports.transition(
            first.id, {ImportStatus.UPLOADED}, ImportStatus.FAILED, NOW, "x"
        )
        await uow.commit()

    async with factory() as uow:
        second = await uow.imports.add(new_import(), NOW)
        await uow.commit()
        found = await uow.imports.find_by_hash("a" * 64)

    assert found is not None
    assert found.id == second.id


async def test_transitions_only_apply_from_the_expected_states(factory: Factory) -> None:
    async with factory() as uow:
        added = await uow.imports.add(new_import(), NOW)
        wrong = await uow.imports.transition(
            added.id, {ImportStatus.VALIDATED}, ImportStatus.QUEUED, NOW
        )
        right = await uow.imports.transition(
            added.id, {ImportStatus.UPLOADED}, ImportStatus.VALIDATING, LATER
        )
        await uow.commit()
        current = await uow.imports.get(added.id)

    assert (wrong, right) == (False, True)
    assert current is not None
    assert (current.status, current.updated_at) == (ImportStatus.VALIDATING, LATER)


async def test_the_terminal_and_confirmation_timestamps_are_set(factory: Factory) -> None:
    async with factory() as uow:
        added = await uow.imports.add(new_import(), NOW)
        await uow.imports.transition(added.id, {ImportStatus.UPLOADED}, ImportStatus.QUEUED, LATER)
        await uow.imports.transition(added.id, {ImportStatus.QUEUED}, ImportStatus.COMPLETED, LATER)
        await uow.commit()
        done = await uow.imports.get(added.id)

    assert done is not None
    assert (done.confirmed_at, done.finished_at) == (LATER, LATER)


def problem(row_number: int, severity: Severity = Severity.ERROR) -> Problem:
    return Problem(severity, row_number, "price", "free", "not_a_number", "bad price")


async def test_a_validation_result_is_saved_once_with_its_problems_and_snapshot(
    factory: Factory,
) -> None:
    category = CategoryRef(uuid4(), "Footwear")
    summary = ImportSummary(rejected=False, rows_read=3, importable_rows=2, to_create=2)
    async with factory() as uow:
        added = await uow.imports.add(new_import(), NOW)
        await uow.imports.transition(
            added.id, {ImportStatus.UPLOADED}, ImportStatus.VALIDATING, NOW
        )
        saved = await uow.imports.save_validation(
            added.id,
            ImportStatus.VALIDATED,
            summary,
            [problem(2), problem(3, Severity.WARNING)],
            [category],
            LATER,
        )
        await uow.commit()
        record = await uow.imports.get(added.id)
        snapshot = await uow.imports.category_snapshot(added.id)
        stored = await uow.imports.problems(added.id, None, None, 10)
        warnings = await uow.imports.problems(added.id, "warning", None, 10)
        after_first = await uow.imports.problems(added.id, None, stored[0].id, 10)

    assert saved
    assert record is not None
    assert (record.status, record.summary, record.validated_at) == (
        ImportStatus.VALIDATED,
        summary,
        LATER,
    )
    assert snapshot == [category]
    assert [item.row for item in stored] == [2, 3]
    assert [item.row for item in warnings] == [3]
    assert [item.row for item in after_first] == [3]


async def test_a_validation_result_is_refused_when_the_import_is_no_longer_validating(
    factory: Factory,
) -> None:
    async with factory() as uow:
        added = await uow.imports.add(new_import(), NOW)
        await uow.imports.transition(
            added.id, {ImportStatus.UPLOADED}, ImportStatus.FAILED, NOW, "x"
        )
        saved = await uow.imports.save_validation(
            added.id, ImportStatus.VALIDATED, ImportSummary(rejected=False), [problem(2)], [], NOW
        )

    assert not saved


async def test_validating_again_replaces_the_problems(factory: Factory) -> None:
    async with factory() as uow:
        added = await uow.imports.add(new_import(), NOW)
        for rows in ([2, 3], [9]):
            await uow.imports.transition(
                added.id,
                {ImportStatus.UPLOADED, ImportStatus.VALIDATED},
                ImportStatus.VALIDATING,
                NOW,
            )
            await uow.imports.save_validation(
                added.id,
                ImportStatus.VALIDATED,
                ImportSummary(rejected=False),
                [problem(number) for number in rows],
                [],
                NOW,
            )
        stored = await uow.imports.problems(added.id, None, None, 10)

    assert [item.row for item in stored] == [9]


async def test_progress_is_recorded_on_the_import(factory: Factory) -> None:
    async with factory() as uow:
        added = await uow.imports.add(new_import(), NOW)
        await uow.imports.record_progress(added.id, Progress(10, 4, 3, 2, 1), LATER)
        await uow.commit()
        record = await uow.imports.get(added.id)

    assert record is not None
    assert record.progress == Progress(10, 4, 3, 2, 1)


async def test_an_import_and_its_event_are_committed_together_and_discarded_together(
    factory: Factory,
) -> None:
    identifier = uuid4()
    async with factory() as uow:
        await uow.imports.add(new_import(identifier=identifier), NOW)
        await uow.events.add(
            topic=IMPORTS_TOPIC,
            key=str(identifier),
            event_type="import.requested",
            payload=ImportRequestedV1(
                import_id=identifier, object_key="imports/x/source.csv", sha256="a" * 64
            ),
            correlation_id=uuid4(),
        )

    assert await scalar(factory, "SELECT count(*) FROM imports") == 0
    assert await scalar(factory, "SELECT count(*) FROM outbox") == 0

    async with factory() as uow:
        await uow.imports.add(new_import(identifier=identifier), NOW)
        await uow.events.add(
            topic=IMPORTS_TOPIC,
            key=str(identifier),
            event_type="import.requested",
            payload=ImportRequestedV1(
                import_id=identifier, object_key="imports/x/source.csv", sha256="a" * 64
            ),
            correlation_id=uuid4(),
        )
        await uow.commit()

    assert await scalar(factory, "SELECT count(*) FROM imports") == 1
    assert await scalar(factory, "SELECT count(*) FROM outbox WHERE topic = 'imports.jobs'") == 1


async def test_the_database_refuses_an_unknown_status(factory: Factory) -> None:
    async with factory() as uow:
        with pytest.raises(IntegrityError):
            await uow._session.execute(
                text(
                    "INSERT INTO imports "
                    "(filename, object_key, sha256, size_bytes, status, created_by) "
                    "VALUES ('f', 'k', :sha, 1, 'whatever', 'x')"
                ),
                {"sha": "b" * 64},
            )


async def saved_validation(factory: Factory) -> UUID:
    async with factory() as uow:
        added = await uow.imports.add(new_import(), NOW)
        await uow.imports.transition(
            added.id, {ImportStatus.UPLOADED}, ImportStatus.VALIDATING, NOW
        )
        await uow.imports.save_validation(
            added.id,
            ImportStatus.VALIDATED,
            ImportSummary(rejected=False, rows_read=3, error_rows=2),
            [problem(2), problem(3), problem(4, Severity.WARNING)],
            [CategoryRef(uuid4(), "Footwear")],
            NOW,
        )
        await uow.commit()
    return added.id


async def test_restarting_the_validation_discards_the_report_problems_and_snapshot_together(
    factory: Factory,
) -> None:
    import_id = await saved_validation(factory)

    async with factory() as uow:
        restarted = await uow.imports.restart_validation(
            import_id, {ImportStatus.REJECTED, ImportStatus.VALIDATED}, LATER
        )
        await uow.commit()

    assert restarted
    assert await scalar(factory, "SELECT count(*) FROM import_problems") == 0
    row = await scalar(
        factory,
        "SELECT status || '|' || (report IS NULL)::text || '|' || (category_snapshot IS NULL)::text"
        " || '|' || (validated_at IS NULL)::text FROM imports WHERE id = :id",
        id=import_id,
    )
    assert row == "uploaded|true|true|true"
    assert (
        await scalar(factory, "SELECT updated_at FROM imports WHERE id = :id", id=import_id)
        == LATER
    )


async def test_restarting_the_validation_is_all_or_nothing(factory: Factory) -> None:
    import_id = await saved_validation(factory)

    async with factory() as uow:
        assert await uow.imports.restart_validation(import_id, {ImportStatus.VALIDATED}, LATER)

    async with factory() as uow:
        record = await uow.imports.get(import_id)
        stored = await uow.imports.problems(import_id, None, None, 10)
        snapshot = await uow.imports.category_snapshot(import_id)

    assert record is not None
    assert record.status is ImportStatus.VALIDATED
    assert record.summary is not None
    assert len(stored) == 3
    assert len(snapshot) == 1


async def test_restarting_the_validation_only_applies_from_the_expected_states(
    factory: Factory,
) -> None:
    import_id = await saved_validation(factory)
    async with factory() as uow:
        await uow.imports.transition(import_id, {ImportStatus.VALIDATED}, ImportStatus.QUEUED, NOW)
        refused = await uow.imports.restart_validation(
            import_id, {ImportStatus.REJECTED, ImportStatus.VALIDATED}, LATER
        )
        await uow.commit()

    assert not refused
    assert await scalar(factory, "SELECT count(*) FROM import_problems") == 3
    assert await scalar(
        factory, "SELECT report IS NOT NULL FROM imports WHERE id = :id", id=import_id
    )


async def test_only_one_of_two_concurrent_restarts_wins(factory: Factory) -> None:
    import_id = await saved_validation(factory)
    expected = {ImportStatus.REJECTED, ImportStatus.VALIDATED}

    async def restart() -> bool:
        async with factory() as uow:
            won = await uow.imports.restart_validation(import_id, expected, LATER)
            await uow.commit()
            return won

    results = await asyncio.gather(restart(), restart())

    assert sorted(results) == [False, True]
    assert await scalar(factory, "SELECT count(*) FROM import_problems") == 0
