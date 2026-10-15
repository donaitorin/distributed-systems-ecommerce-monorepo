import asyncio
import hashlib
import logging
from collections.abc import Callable, Iterable, Iterator
from dataclasses import replace
from datetime import datetime
from itertools import batched
from uuid import UUID

from catalog.application.ports import UnitOfWorkFactory
from catalog.application.products import utc_now
from catalog.domain.csv_import import (
    CategoryIndex,
    ImportAnalysis,
    ImportReport,
    analyze,
    iter_importable_rows,
)
from catalog.domain.errors import DomainError
from catalog.domain.imports import (
    BATCH_SIZE,
    CategoryRef,
    ImportStatus,
    ImportSummary,
    Progress,
    UnknownCategorySummary,
    classify,
)
from catalog.domain.product import Category
from ecommerce_storage import ObjectStorage

logger = logging.getLogger(__name__)


class ImportFileChangedError(DomainError):
    def __init__(self, import_id: UUID) -> None:
        super().__init__(f"the stored file of import {import_id} no longer matches its hash")


class HashingChunks:
    def __init__(self, source: Iterable[bytes]) -> None:
        self._source = source
        self._hasher = hashlib.sha256()

    def __iter__(self) -> Iterator[bytes]:
        for chunk in self._source:
            self._hasher.update(chunk)
            yield chunk

    def hexdigest(self) -> str:
        return self._hasher.hexdigest()


def summary_of(report: ImportReport) -> ImportSummary:
    return ImportSummary(
        rejected=report.rejected,
        rows_read=report.rows_read,
        blank_rows=report.blank_rows,
        error_rows=report.error_rows,
        error_count=report.error_count,
        warning_count=report.warning_count,
        superseded_rows=report.superseded_rows,
        duplicate_rows=report.duplicate_rows,
        importable_rows=report.importable_rows,
        truncated=report.truncated,
        unknown_categories=tuple(
            UnknownCategorySummary(item.value, item.rows, item.suggestion)
            for item in report.unknown_categories
        ),
    )


class ImportJobs:
    def __init__(
        self,
        unit_of_work: UnitOfWorkFactory,
        storage: ObjectStorage,
        clock: Callable[[], datetime] = utc_now,
        batch_size: int = BATCH_SIZE,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._storage = storage
        self._clock = clock
        self._batch_size = batch_size

    async def validate(self, import_id: UUID) -> None:
        async with self._unit_of_work() as uow:
            moved = await uow.imports.transition(
                import_id,
                {ImportStatus.UPLOADED, ImportStatus.VALIDATING},
                ImportStatus.VALIDATING,
                self._clock(),
            )
            record = await uow.imports.get(import_id)
            categories = await uow.categories.list_all()
            await uow.commit()
        if not moved or record is None:
            logger.info("validation skipped", extra={"import_id": str(import_id)})
            return
        index = CategoryIndex.of(categories)
        snapshot = [CategoryRef(item.id, item.name) for item in categories]
        analysis, digest = await asyncio.to_thread(self._analyze, record.object_key, index)
        if not analysis.report.rejected and digest != record.sha256:
            raise ImportFileChangedError(import_id)
        summary = summary_of(analysis.report)
        status = ImportStatus.REJECTED if summary.rejected else ImportStatus.VALIDATED
        if not summary.rejected:
            summary = await self._with_preview(record.object_key, index, analysis, summary)
        async with self._unit_of_work() as uow:
            saved = await uow.imports.save_validation(
                import_id, status, summary, analysis.report.problems, snapshot, self._clock()
            )
            await uow.commit()
        if not saved:
            logger.info("validation result discarded", extra={"import_id": str(import_id)})

    async def fail(self, import_id: UUID, reason: str) -> None:
        async with self._unit_of_work() as uow:
            await uow.imports.transition(
                import_id,
                {
                    ImportStatus.UPLOADED,
                    ImportStatus.VALIDATING,
                    ImportStatus.QUEUED,
                    ImportStatus.PROCESSING,
                },
                ImportStatus.FAILED,
                self._clock(),
                failure_reason=reason,
            )
            await uow.commit()

    async def process(self, import_id: UUID) -> None:
        async with self._unit_of_work() as uow:
            moved = await uow.imports.transition(
                import_id,
                {ImportStatus.QUEUED, ImportStatus.PROCESSING},
                ImportStatus.PROCESSING,
                self._clock(),
            )
            record = await uow.imports.get(import_id)
            snapshot = await uow.imports.category_snapshot(import_id)
            if moved:
                await uow.imports.record_progress(import_id, Progress(), self._clock())
            await uow.commit()
        if not moved or record is None:
            logger.info("processing skipped", extra={"import_id": str(import_id)})
            return
        index = CategoryIndex.of(Category(item.id, item.name, "") for item in snapshot)
        analysis, digest = await asyncio.to_thread(self._analyze, record.object_key, index)
        if analysis.report.rejected or digest != record.sha256:
            raise ImportFileChangedError(import_id)
        rows = iter_importable_rows(
            self._storage.read_chunks(record.object_key), index, analysis.winners
        )
        batches = batched(rows, self._batch_size, strict=False)
        progress = Progress()
        while (batch := await asyncio.to_thread(next, batches, None)) is not None:
            async with self._unit_of_work() as uow:
                progress = progress.plus(await uow.products.upsert_many(batch, self._clock()))
                await uow.imports.record_progress(import_id, progress, self._clock())
                await uow.commit()
        async with self._unit_of_work() as uow:
            await uow.imports.transition(
                import_id, {ImportStatus.PROCESSING}, ImportStatus.COMPLETED, self._clock()
            )
            await uow.commit()

    def _analyze(self, key: str, index: CategoryIndex) -> tuple[ImportAnalysis, str]:
        chunks = HashingChunks(self._storage.read_chunks(key))
        analysis = analyze(chunks, index)
        return analysis, chunks.hexdigest()

    async def _with_preview(
        self, key: str, index: CategoryIndex, analysis: ImportAnalysis, summary: ImportSummary
    ) -> ImportSummary:
        rows = iter_importable_rows(self._storage.read_chunks(key), index, analysis.winners)
        batches = batched(rows, self._batch_size, strict=False)
        totals = [0, 0, 0, 0]
        while (batch := await asyncio.to_thread(next, batches, None)) is not None:
            async with self._unit_of_work() as uow:
                existing = await uow.products.existing([row.product.sku for row in batch])
            for position, count in enumerate(classify(batch, existing)):
                totals[position] += count
        return replace(
            summary,
            to_create=totals[0],
            to_update=totals[1],
            to_restore=totals[2],
            unchanged=totals[3],
        )
