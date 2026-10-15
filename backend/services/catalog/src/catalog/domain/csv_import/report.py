from dataclasses import dataclass, field

from catalog.domain.csv_import.problems import Problem


@dataclass(frozen=True, slots=True)
class UnknownCategory:
    value: str
    rows: int
    suggestion: str | None


@dataclass(frozen=True, slots=True)
class ImportReport:
    rejected: bool
    rows_read: int = 0
    blank_rows: int = 0
    error_rows: int = 0
    superseded_rows: int = 0
    duplicate_rows: int = 0
    importable_rows: int = 0
    error_count: int = 0
    warning_count: int = 0
    problems: tuple[Problem, ...] = ()
    truncated: bool = False
    unknown_categories: tuple[UnknownCategory, ...] = field(default=())

    @property
    def skipped_rows(self) -> int:
        return self.superseded_rows + self.duplicate_rows
