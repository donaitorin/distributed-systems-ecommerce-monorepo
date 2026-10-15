from collections.abc import Collection, Sequence
from dataclasses import asdict
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

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
    UnknownCategorySummary,
)
from catalog.infra.models import ImportModel, ImportProblemModel

SHA_INDEX = "uq_imports_sha256_unless_failed"
INSERT_CHUNK = 1000


def summary_to_json(summary: ImportSummary) -> dict[str, Any]:
    return asdict(summary)


def summary_from_json(raw: dict[str, Any]) -> ImportSummary:
    unknown = tuple(UnknownCategorySummary(**item) for item in raw.get("unknown_categories", ()))
    return ImportSummary(**{**raw, "unknown_categories": unknown})


def to_record(model: ImportModel) -> ImportRecord:
    return ImportRecord(
        id=model.id,
        filename=model.filename,
        object_key=model.object_key,
        sha256=model.sha256,
        size_bytes=model.size_bytes,
        status=ImportStatus(model.status),
        created_by=model.created_by,
        created_at=model.created_at,
        updated_at=model.updated_at,
        failure_reason=model.failure_reason,
        summary=summary_from_json(model.report) if model.report is not None else None,
        progress=Progress(
            model.processed_rows,
            model.created_rows,
            model.updated_rows,
            model.restored_rows,
            model.unchanged_rows,
        ),
        validated_at=model.validated_at,
        confirmed_at=model.confirmed_at,
        finished_at=model.finished_at,
    )


class SqlImportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, new: NewImport, now: datetime) -> ImportRecord:
        model = ImportModel(
            id=new.id,
            filename=new.filename,
            object_key=new.object_key,
            sha256=new.sha256,
            size_bytes=new.size_bytes,
            status=ImportStatus.UPLOADED.value,
            created_by=new.created_by,
            created_at=now,
            updated_at=now,
        )
        self._session.add(model)
        try:
            await self._session.flush()
        except IntegrityError as error:
            if SHA_INDEX in str(error.orig):
                raise DuplicateImportError(new.sha256) from error
            raise
        return to_record(model)

    async def get(self, import_id: UUID) -> ImportRecord | None:
        return await self._fetch(import_id, lock=False)

    async def get_for_update(self, import_id: UUID) -> ImportRecord | None:
        return await self._fetch(import_id, lock=True)

    async def find_by_hash(self, sha256: str) -> ImportRecord | None:
        statement = (
            select(ImportModel)
            .where(ImportModel.sha256 == sha256, ImportModel.status != ImportStatus.FAILED.value)
            .execution_options(populate_existing=True)
        )
        model = (await self._session.execute(statement)).scalars().first()
        return to_record(model) if model is not None else None

    async def transition(
        self,
        import_id: UUID,
        expected: Collection[ImportStatus],
        status: ImportStatus,
        now: datetime,
        failure_reason: str | None = None,
    ) -> bool:
        values: dict[str, Any] = {"status": status.value, "updated_at": now}
        if failure_reason is not None:
            values["failure_reason"] = failure_reason
        if status is ImportStatus.QUEUED:
            values["confirmed_at"] = now
        if status in {ImportStatus.COMPLETED, ImportStatus.FAILED}:
            values["finished_at"] = now
        statement = (
            update(ImportModel)
            .where(
                ImportModel.id == import_id,
                ImportModel.status.in_([item.value for item in expected]),
            )
            .values(**values)
        )
        return bool((await self._session.execute(statement)).rowcount)  # type: ignore[attr-defined]

    async def save_validation(
        self,
        import_id: UUID,
        status: ImportStatus,
        summary: ImportSummary,
        problems: Sequence[Problem],
        snapshot: Sequence[CategoryRef],
        now: datetime,
    ) -> bool:
        statement = (
            update(ImportModel)
            .where(ImportModel.id == import_id, ImportModel.status == ImportStatus.VALIDATING.value)
            .values(
                status=status.value,
                report=summary_to_json(summary),
                category_snapshot=[{"id": str(item.id), "name": item.name} for item in snapshot],
                validated_at=now,
                updated_at=now,
            )
        )
        if not (await self._session.execute(statement)).rowcount:  # type: ignore[attr-defined]
            return False
        await self._session.execute(
            delete(ImportProblemModel).where(ImportProblemModel.import_id == import_id)
        )
        rows = [
            {
                "import_id": import_id,
                "severity": item.severity.value,
                "row": item.row,
                "column_name": item.column,
                "value": item.value,
                "code": item.code,
                "reason": item.reason,
            }
            for item in problems
        ]
        for start in range(0, len(rows), INSERT_CHUNK):
            await self._session.execute(
                insert(ImportProblemModel), rows[start : start + INSERT_CHUNK]
            )
        return True

    async def category_snapshot(self, import_id: UUID) -> list[CategoryRef]:
        raw = await self._session.scalar(
            select(ImportModel.category_snapshot).where(ImportModel.id == import_id)
        )
        return [CategoryRef(UUID(item["id"]), item["name"]) for item in raw or ()]

    async def problems(
        self, import_id: UUID, severity: str | None, after_id: int | None, limit: int
    ) -> list[StoredProblem]:
        statement = (
            select(ImportProblemModel)
            .where(ImportProblemModel.import_id == import_id)
            .order_by(ImportProblemModel.id)
            .limit(limit)
        )
        if severity is not None:
            statement = statement.where(ImportProblemModel.severity == severity)
        if after_id is not None:
            statement = statement.where(ImportProblemModel.id > after_id)
        models = (await self._session.scalars(statement)).all()
        return [
            StoredProblem(
                item.id,
                item.severity,
                item.row,
                item.column_name,
                item.value,
                item.code,
                item.reason,
            )
            for item in models
        ]

    async def record_progress(self, import_id: UUID, progress: Progress, now: datetime) -> None:
        await self._session.execute(
            update(ImportModel)
            .where(ImportModel.id == import_id)
            .values(
                processed_rows=progress.processed_rows,
                created_rows=progress.created_rows,
                updated_rows=progress.updated_rows,
                restored_rows=progress.restored_rows,
                unchanged_rows=progress.unchanged_rows,
                updated_at=now,
            )
        )

    async def _fetch(self, import_id: UUID, lock: bool) -> ImportRecord | None:
        statement = (
            select(ImportModel)
            .where(ImportModel.id == import_id)
            .execution_options(populate_existing=True)
        )
        if lock:
            statement = statement.with_for_update()
        model = (await self._session.execute(statement)).scalars().first()
        return to_record(model) if model is not None else None
