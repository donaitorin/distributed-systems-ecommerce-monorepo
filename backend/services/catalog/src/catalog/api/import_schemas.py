from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field

from catalog.domain.imports import ImportRecord, StoredProblem, UnknownCategorySummary


class UnknownCategoryOut(BaseModel):
    value: str
    rows: int
    suggestion: str | None

    @classmethod
    def from_domain(cls, item: UnknownCategorySummary) -> Self:
        return cls(value=item.value, rows=item.rows, suggestion=item.suggestion)


class ImportSummaryOut(BaseModel):
    rejected: bool
    rows_read: int
    blank_rows: int
    error_rows: int
    error_count: int
    warning_count: int
    superseded_rows: int
    duplicate_rows: int
    importable_rows: int
    to_create: int
    to_update: int
    to_restore: int
    unchanged: int
    truncated: bool = Field(
        description="True when only the first problems are stored; the counts stay exact"
    )
    unknown_categories: list[UnknownCategoryOut]


class ProgressOut(BaseModel):
    processed_rows: int
    created_rows: int
    updated_rows: int
    restored_rows: int
    unchanged_rows: int


class ProblemOut(BaseModel):
    severity: str
    row: int | None = Field(description="Spreadsheet row; the header is row 1")
    column: str | None
    value: str | None = Field(description="The value as received, truncated to 200 characters")
    code: str
    reason: str

    @classmethod
    def from_domain(cls, item: StoredProblem) -> Self:
        return cls(
            severity=item.severity,
            row=item.row,
            column=item.column,
            value=item.value,
            code=item.code,
            reason=item.reason,
        )


class ProblemsPageOut(BaseModel):
    items: list[ProblemOut]
    next_cursor: str | None = None


class ImportLinks(BaseModel):
    self: str
    problems: str
    problems_csv: str
    confirm: str | None = Field(
        default=None, description="Present while the import can be confirmed"
    )


class ImportOut(BaseModel):
    id: UUID
    status: str
    filename: str
    size_bytes: int
    sha256: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    validated_at: datetime | None
    confirmed_at: datetime | None
    finished_at: datetime | None
    failure_reason: str | None
    summary: ImportSummaryOut | None
    progress: ProgressOut
    problems: list[ProblemOut] = Field(
        description="The first problems, errors before warnings; use the links for all of them"
    )
    links: ImportLinks

    @classmethod
    def from_domain(cls, record: ImportRecord, preview: list[StoredProblem]) -> Self:
        base = f"/api/v1/imports/{record.id}"
        summary = record.summary
        return cls(
            id=record.id,
            status=record.status.value,
            filename=record.filename,
            size_bytes=record.size_bytes,
            sha256=record.sha256,
            created_by=record.created_by,
            created_at=record.created_at,
            updated_at=record.updated_at,
            validated_at=record.validated_at,
            confirmed_at=record.confirmed_at,
            finished_at=record.finished_at,
            failure_reason=record.failure_reason,
            summary=(
                ImportSummaryOut(
                    rejected=summary.rejected,
                    rows_read=summary.rows_read,
                    blank_rows=summary.blank_rows,
                    error_rows=summary.error_rows,
                    error_count=summary.error_count,
                    warning_count=summary.warning_count,
                    superseded_rows=summary.superseded_rows,
                    duplicate_rows=summary.duplicate_rows,
                    importable_rows=summary.importable_rows,
                    to_create=summary.to_create,
                    to_update=summary.to_update,
                    to_restore=summary.to_restore,
                    unchanged=summary.unchanged,
                    truncated=summary.truncated,
                    unknown_categories=[
                        UnknownCategoryOut.from_domain(item) for item in summary.unknown_categories
                    ],
                )
                if summary is not None
                else None
            ),
            progress=ProgressOut(
                processed_rows=record.progress.processed_rows,
                created_rows=record.progress.created_rows,
                updated_rows=record.progress.updated_rows,
                restored_rows=record.progress.restored_rows,
                unchanged_rows=record.progress.unchanged_rows,
            ),
            problems=[ProblemOut.from_domain(item) for item in preview],
            links=ImportLinks(
                self=base,
                problems=f"{base}/problems",
                problems_csv=f"{base}/problems.csv",
                confirm=(
                    f"{base}/confirm"
                    if record.status.value == "validated"
                    and summary is not None
                    and summary.importable_rows > 0
                    else None
                ),
            ),
        )
