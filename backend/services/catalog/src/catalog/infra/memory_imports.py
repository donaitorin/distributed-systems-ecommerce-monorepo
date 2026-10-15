from collections.abc import Collection, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel

from catalog.application.errors import DuplicateImportError
from catalog.domain.csv_import import Problem
from catalog.domain.imports import (
    CategoryRef,
    ImportRecord,
    ImportStatus,
    ImportSummary,
    NewImport,
    Progress,
    StoredProblem,
)


@dataclass(slots=True)
class OutboxEntry:
    event_id: UUID
    topic: str
    key: str
    event_type: str
    payload: BaseModel
    correlation_id: UUID


@dataclass(slots=True)
class ImportData:
    records: dict[UUID, ImportRecord]
    problems: dict[UUID, list[StoredProblem]]
    snapshots: dict[UUID, list[CategoryRef]]
    outbox: list[OutboxEntry]
    next_problem_id: int = 1


def empty_import_data() -> ImportData:
    return ImportData({}, {}, {}, [])


class InMemoryImportRepository:
    def __init__(self, data: ImportData) -> None:
        self._data = data

    async def add(self, new: NewImport, now: datetime) -> ImportRecord:
        if any(
            item.sha256 == new.sha256 and item.status is not ImportStatus.FAILED
            for item in self._data.records.values()
        ):
            raise DuplicateImportError(new.sha256)
        record = ImportRecord(
            id=new.id,
            filename=new.filename,
            object_key=new.object_key,
            sha256=new.sha256,
            size_bytes=new.size_bytes,
            status=ImportStatus.UPLOADED,
            created_by=new.created_by,
            created_at=now,
            updated_at=now,
        )
        self._data.records[new.id] = record
        return record

    async def get(self, import_id: UUID) -> ImportRecord | None:
        return self._data.records.get(import_id)

    async def get_for_update(self, import_id: UUID) -> ImportRecord | None:
        return self._data.records.get(import_id)

    async def find_by_hash(self, sha256: str) -> ImportRecord | None:
        for record in self._data.records.values():
            if record.sha256 == sha256 and record.status is not ImportStatus.FAILED:
                return record
        return None

    async def transition(
        self,
        import_id: UUID,
        expected: Collection[ImportStatus],
        status: ImportStatus,
        now: datetime,
        failure_reason: str | None = None,
    ) -> bool:
        record = self._data.records.get(import_id)
        if record is None or record.status not in expected:
            return False
        changes: dict[str, object] = {"status": status, "updated_at": now}
        if failure_reason is not None:
            changes["failure_reason"] = failure_reason
        if status is ImportStatus.QUEUED:
            changes["confirmed_at"] = now
        if status in {ImportStatus.COMPLETED, ImportStatus.FAILED}:
            changes["finished_at"] = now
        self._data.records[import_id] = replace(record, **changes)  # type: ignore[arg-type]
        return True

    async def save_validation(
        self,
        import_id: UUID,
        status: ImportStatus,
        summary: ImportSummary,
        problems: Sequence[Problem],
        snapshot: Sequence[CategoryRef],
        now: datetime,
    ) -> bool:
        record = self._data.records.get(import_id)
        if record is None or record.status is not ImportStatus.VALIDATING:
            return False
        self._data.records[import_id] = replace(
            record, status=status, summary=summary, validated_at=now, updated_at=now
        )
        self._data.snapshots[import_id] = list(snapshot)
        stored: list[StoredProblem] = []
        for item in problems:
            stored.append(
                StoredProblem(
                    self._data.next_problem_id,
                    item.severity.value,
                    item.row,
                    item.column,
                    item.value,
                    item.code,
                    item.reason,
                )
            )
            self._data.next_problem_id += 1
        self._data.problems[import_id] = stored
        return True

    async def category_snapshot(self, import_id: UUID) -> list[CategoryRef]:
        return list(self._data.snapshots.get(import_id, []))

    async def problems(
        self, import_id: UUID, severity: str | None, after_id: int | None, limit: int
    ) -> list[StoredProblem]:
        found = [
            item
            for item in self._data.problems.get(import_id, [])
            if (severity is None or item.severity == severity)
            and (after_id is None or item.id > after_id)
        ]
        return found[:limit]

    async def record_progress(self, import_id: UUID, progress: Progress, now: datetime) -> None:
        record = self._data.records[import_id]
        self._data.records[import_id] = replace(record, progress=progress, updated_at=now)


class InMemoryEventOutbox:
    def __init__(self, data: ImportData) -> None:
        self._data = data

    async def add(
        self, *, topic: str, key: str, event_type: str, payload: BaseModel, correlation_id: UUID
    ) -> None:
        self._data.outbox.append(
            OutboxEntry(uuid4(), topic, key, event_type, payload, correlation_id)
        )
