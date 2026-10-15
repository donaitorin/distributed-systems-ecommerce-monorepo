from dataclasses import dataclass
from enum import StrEnum
from typing import Final

VALUE_LIMIT: Final = 200

EMPTY_FILE: Final = "empty_file"
NOT_TEXT: Final = "not_text"
INVALID_ENCODING: Final = "invalid_encoding"
MALFORMED_CSV: Final = "malformed_csv"
MISSING_COLUMN: Final = "missing_column"
UNKNOWN_COLUMN: Final = "unknown_column"
DUPLICATE_COLUMN: Final = "duplicate_column"
NO_ROWS: Final = "no_rows"

COLUMN_COUNT: Final = "column_count"
REQUIRED: Final = "required"
NOT_A_NUMBER: Final = "not_a_number"
NOT_AN_INTEGER: Final = "not_an_integer"
UNKNOWN_CATEGORY: Final = "unknown_category"

PRICE_NORMALIZED: Final = "price_normalized"
SKU_UPPERCASED: Final = "sku_uppercased"
SUPERSEDED: Final = "superseded"
SUPERSEDED_BY_INVALID: Final = "superseded_by_invalid"


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class Problem:
    severity: Severity
    row: int | None
    column: str | None
    value: str | None
    code: str
    reason: str


def received(value: str | None) -> str | None:
    if value is None or len(value) <= VALUE_LIMIT:
        return value
    return value[: VALUE_LIMIT - 1] + "…"


def error(
    row: int | None, column: str | None, value: str | None, code: str, reason: str
) -> Problem:
    return Problem(Severity.ERROR, row, column, received(value), code, reason)


def warning(
    row: int | None, column: str | None, value: str | None, code: str, reason: str
) -> Problem:
    return Problem(Severity.WARNING, row, column, received(value), code, reason)
