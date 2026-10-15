import base64
import binascii
import csv
import hashlib
import io
import logging
import re
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Final
from uuid import UUID, uuid4

from catalog.application.cursors import INVALID_CURSOR, InvalidCursorError
from catalog.application.errors import (
    DuplicateImportError,
    ImportNotConfirmableError,
    ImportNotFoundError,
    ImportTooLargeError,
)
from catalog.application.ports import UnitOfWorkFactory
from catalog.application.products import utc_now
from catalog.domain.imports import (
    CONFIRMED_STATUSES,
    SOURCE_CONTENT_TYPE,
    ImportRecord,
    ImportStatus,
    NewImport,
    StoredProblem,
    UploadResult,
    clean_filename,
    import_object_key,
)
from ecommerce_contracts import (
    IMPORT_REQUESTED,
    IMPORT_VALIDATION_REQUESTED,
    IMPORTS_TOPIC,
    ImportRequestedV1,
    ImportValidationRequestedV1,
)
from ecommerce_storage import ObjectStorage

logger = logging.getLogger(__name__)

CSV_BOM: Final = "﻿"
PROBLEM_COLUMNS: Final = ("severity", "row", "column", "value", "code", "reason")
CSV_BATCH: Final = 500
PLAIN_NUMBER: Final = re.compile(r"[+-][0-9]+(?:\.[0-9]+)?")
FORMULA_STARTS: Final = ("=", "+", "-", "@", "\t", "\r")


class MeteredChunks:
    def __init__(self, source: AsyncIterator[bytes], limit_bytes: int) -> None:
        self._source = source
        self._limit = limit_bytes
        self._hasher = hashlib.sha256()
        self.size = 0

    def __aiter__(self) -> "MeteredChunks":
        return self

    async def __anext__(self) -> bytes:
        chunk = await self._source.__anext__()
        self.size += len(chunk)
        if self.size > self._limit:
            raise ImportTooLargeError(self._limit)
        self._hasher.update(chunk)
        return chunk

    def hexdigest(self) -> str:
        return self._hasher.hexdigest()


@dataclass(frozen=True, slots=True)
class ProblemsPage:
    items: list[StoredProblem]
    next_cursor: str | None


def encode_problem_cursor(last_id: int) -> str:
    return base64.urlsafe_b64encode(str(last_id).encode()).decode().rstrip("=")


def decode_problem_cursor(raw: str) -> int:
    try:
        padded = raw + "=" * (-len(raw) % 4)
        value = int(base64.urlsafe_b64decode(padded).decode())
    except (binascii.Error, ValueError, UnicodeDecodeError) as error:
        raise InvalidCursorError(INVALID_CURSOR, "cursor is malformed") from error
    if value < 0:
        raise InvalidCursorError(INVALID_CURSOR, "cursor is malformed")
    return value


def neutralize_formula(value: str | None) -> str:
    if value is None:
        return ""
    if value.startswith(FORMULA_STARTS) and not PLAIN_NUMBER.fullmatch(value):
        return "'" + value
    return value


def problem_csv_row(problem: StoredProblem) -> list[str]:
    return [
        problem.severity,
        "" if problem.row is None else str(problem.row),
        neutralize_formula(problem.column),
        neutralize_formula(problem.value),
        problem.code,
        neutralize_formula(problem.reason),
    ]


class ImportService:
    def __init__(
        self,
        unit_of_work: UnitOfWorkFactory,
        storage: ObjectStorage,
        max_bytes: int,
        clock: Callable[[], datetime] = utc_now,
        new_id: Callable[[], UUID] = uuid4,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._storage = storage
        self._max_bytes = max_bytes
        self._clock = clock
        self._new_id = new_id

    @property
    def max_bytes(self) -> int:
        return self._max_bytes

    async def upload(
        self,
        chunks: AsyncIterator[bytes],
        created_by: str,
        correlation_id: UUID,
        filename_of: Callable[[], str | None] = lambda: None,
    ) -> UploadResult:
        import_id = self._new_id()
        key = import_object_key(import_id)
        metered = MeteredChunks(chunks, self._max_bytes)
        await self._storage.put_stream(key, metered, SOURCE_CONTENT_TYPE)
        digest = metered.hexdigest()
        new = NewImport(
            import_id, clean_filename(filename_of()), key, digest, metered.size, created_by
        )
        try:
            existing = await self._find_by_hash(digest)
            if existing is not None:
                await self._discard(key)
                return UploadResult(existing, False)
            return UploadResult(await self._register(new, correlation_id), True)
        except DuplicateImportError:
            await self._discard(key)
            existing = await self._find_by_hash(digest)
            if existing is None:
                raise
            return UploadResult(existing, False)
        except BaseException:
            await self._discard(key)
            raise

    async def get(self, import_id: UUID) -> ImportRecord:
        async with self._unit_of_work() as uow:
            record = await uow.imports.get(import_id)
        if record is None:
            raise ImportNotFoundError(import_id)
        return record

    async def preview(
        self, import_id: UUID, limit: int
    ) -> tuple[ImportRecord, list[StoredProblem]]:
        async with self._unit_of_work() as uow:
            record = await uow.imports.get(import_id)
            if record is None:
                raise ImportNotFoundError(import_id)
            errors = await uow.imports.problems(import_id, "error", None, limit)
            warnings = await uow.imports.problems(import_id, "warning", None, limit - len(errors))
        return record, (errors + warnings)[:limit]

    async def problems(
        self, import_id: UUID, severity: str | None, cursor: str | None, limit: int
    ) -> ProblemsPage:
        after = decode_problem_cursor(cursor) if cursor is not None else None
        async with self._unit_of_work() as uow:
            if await uow.imports.get(import_id) is None:
                raise ImportNotFoundError(import_id)
            found = await uow.imports.problems(import_id, severity, after, limit + 1)
        page = found[:limit]
        more = len(found) > limit
        return ProblemsPage(page, encode_problem_cursor(page[-1].id) if more and page else None)

    async def problems_csv(self, import_id: UUID) -> AsyncIterator[bytes]:
        await self.get(import_id)
        header = io.StringIO()
        csv.writer(header, lineterminator="\r\n").writerow(PROBLEM_COLUMNS)
        yield (CSV_BOM + header.getvalue()).encode()
        after: int | None = None
        while True:
            async with self._unit_of_work() as uow:
                batch = await uow.imports.problems(import_id, None, after, CSV_BATCH)
            if not batch:
                return
            buffer = io.StringIO()
            writer = csv.writer(buffer, lineterminator="\r\n")
            for problem in batch:
                writer.writerow(problem_csv_row(problem))
            yield buffer.getvalue().encode()
            after = batch[-1].id

    async def confirm(self, import_id: UUID, correlation_id: UUID) -> ImportRecord:
        async with self._unit_of_work() as uow:
            record = await uow.imports.get_for_update(import_id)
            if record is None:
                raise ImportNotFoundError(import_id)
            if record.status in CONFIRMED_STATUSES:
                return record
            _require_confirmable(record)
            await uow.imports.transition(
                import_id, {ImportStatus.VALIDATED}, ImportStatus.QUEUED, self._clock()
            )
            await uow.events.add(
                topic=IMPORTS_TOPIC,
                key=str(import_id),
                event_type=IMPORT_REQUESTED,
                payload=ImportRequestedV1(
                    import_id=import_id, object_key=record.object_key, sha256=record.sha256
                ),
                correlation_id=correlation_id,
            )
            await uow.commit()
            confirmed = await uow.imports.get(import_id)
        assert confirmed is not None
        return confirmed

    async def _find_by_hash(self, digest: str) -> ImportRecord | None:
        async with self._unit_of_work() as uow:
            return await uow.imports.find_by_hash(digest)

    async def _register(self, new: NewImport, correlation_id: UUID) -> ImportRecord:
        async with self._unit_of_work() as uow:
            record = await uow.imports.add(new, self._clock())
            await uow.events.add(
                topic=IMPORTS_TOPIC,
                key=str(new.id),
                event_type=IMPORT_VALIDATION_REQUESTED,
                payload=ImportValidationRequestedV1(
                    import_id=new.id, object_key=new.object_key, sha256=new.sha256
                ),
                correlation_id=correlation_id,
            )
            await uow.commit()
        return record

    async def _discard(self, key: str) -> None:
        try:
            await self._storage.delete(key)
        except Exception:
            logger.warning("import file cleanup failed, object left orphaned", extra={"key": key})


def _require_confirmable(record: ImportRecord) -> None:
    if record.status is not ImportStatus.VALIDATED:
        reasons = {
            ImportStatus.UPLOADED: "the file has not been validated yet; check again shortly",
            ImportStatus.VALIDATING: "the file is still being validated; check again shortly",
            ImportStatus.REJECTED: "the file was rejected as a whole; correct it and upload again",
            ImportStatus.FAILED: "the import failed; upload the file again",
        }
        raise ImportNotConfirmableError(record.status.value, reasons[record.status])
    if record.summary is None or record.summary.importable_rows == 0:
        raise ImportNotConfirmableError(record.status.value, "the file has no valid rows to import")
