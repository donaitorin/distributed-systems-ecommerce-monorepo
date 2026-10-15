from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Final
from uuid import UUID

from catalog.domain.csv_import import ImportableRow
from catalog.domain.product import ProductData

DEFAULT_IMPORT_MAX_BYTES: Final = 50 * 1024 * 1024
BATCH_SIZE: Final = 1000
PREVIEW_PROBLEMS: Final = 100
PROBLEMS_PAGE_SIZES: Final = (25, 50, 100, 500)
SOURCE_CONTENT_TYPE: Final = "text/csv"
FILENAME_LIMIT: Final = 255
DEFAULT_FILENAME: Final = "products.csv"


class ImportStatus(StrEnum):
    UPLOADED = "uploaded"
    VALIDATING = "validating"
    REJECTED = "rejected"
    VALIDATED = "validated"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


TERMINAL_STATUSES: Final = frozenset(
    {ImportStatus.REJECTED, ImportStatus.COMPLETED, ImportStatus.FAILED}
)
CONFIRMED_STATUSES: Final = frozenset(
    {ImportStatus.QUEUED, ImportStatus.PROCESSING, ImportStatus.COMPLETED}
)


@dataclass(frozen=True, slots=True)
class CategoryRef:
    id: UUID
    name: str


@dataclass(frozen=True, slots=True)
class UnknownCategorySummary:
    value: str
    rows: int
    suggestion: str | None


@dataclass(frozen=True, slots=True)
class ImportSummary:
    rejected: bool
    rows_read: int = 0
    blank_rows: int = 0
    error_rows: int = 0
    error_count: int = 0
    warning_count: int = 0
    superseded_rows: int = 0
    duplicate_rows: int = 0
    importable_rows: int = 0
    to_create: int = 0
    to_update: int = 0
    to_restore: int = 0
    unchanged: int = 0
    truncated: bool = False
    unknown_categories: tuple[UnknownCategorySummary, ...] = ()


@dataclass(frozen=True, slots=True)
class Progress:
    processed_rows: int = 0
    created_rows: int = 0
    updated_rows: int = 0
    restored_rows: int = 0
    unchanged_rows: int = 0

    def plus(self, other: "Progress") -> "Progress":
        return Progress(
            self.processed_rows + other.processed_rows,
            self.created_rows + other.created_rows,
            self.updated_rows + other.updated_rows,
            self.restored_rows + other.restored_rows,
            self.unchanged_rows + other.unchanged_rows,
        )


@dataclass(frozen=True, slots=True)
class NewImport:
    id: UUID
    filename: str
    object_key: str
    sha256: str
    size_bytes: int
    created_by: str


@dataclass(frozen=True, slots=True)
class ImportRecord:
    id: UUID
    filename: str
    object_key: str
    sha256: str
    size_bytes: int
    status: ImportStatus
    created_by: str
    created_at: datetime
    updated_at: datetime
    failure_reason: str | None = None
    summary: ImportSummary | None = None
    progress: Progress = field(default_factory=Progress)
    validated_at: datetime | None = None
    confirmed_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class StoredProblem:
    id: int
    severity: str
    row: int | None
    column: str | None
    value: str | None
    code: str
    reason: str


@dataclass(frozen=True, slots=True)
class UploadResult:
    record: ImportRecord
    created: bool


def import_object_key(import_id: UUID) -> str:
    return f"imports/{import_id}/source.csv"


def clean_filename(raw: str | None) -> str:
    if not raw:
        return DEFAULT_FILENAME
    name = raw.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = "".join(char for char in name if char.isprintable()).strip()
    return cleaned[:FILENAME_LIMIT] or DEFAULT_FILENAME


@dataclass(frozen=True, slots=True)
class ExistingProduct:
    deleted: bool
    data: ProductData


def classify(
    rows: Iterable[ImportableRow], existing: Mapping[str, ExistingProduct]
) -> tuple[int, int, int, int]:
    created = updated = restored = unchanged = 0
    for row in rows:
        state = existing.get(row.product.sku)
        if state is None:
            created += 1
        elif state.deleted:
            restored += 1
        elif state.data == row.product.data:
            unchanged += 1
        else:
            updated += 1
    return created, updated, restored, unchanged
