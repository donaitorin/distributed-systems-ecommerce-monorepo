import csv
import io
from collections.abc import Iterable, Sequence
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from catalog.domain.csv_import import (
    CategoryIndex,
    ImportableRow,
    ImportAnalysis,
    Problem,
    Severity,
    analyze,
    iter_importable_rows,
)
from catalog.domain.product import Category

HEADER = ("name", "sku", "description", "category", "price", "stock", "weight_kg")
CATEGORY_NAMES = (
    "Accessories",
    "Beauty",
    "Books",
    "Clothing",
    "Electronics",
    "Food & Beverage",
    "Footwear",
    "Games",
    "Gifts",
    "Health",
    "Home & Office",
    "Kitchen",
    "Misc",
    "Outdoors",
    "Pets",
    "Sports",
    "Stationery",
    "Tools",
)
SAMPLE_FILE = Path(__file__).resolve().parents[6] / "data" / "sample-products.csv"
BLANK = ["", "", "", "", "", "", ""]


def categories() -> CategoryIndex:
    return CategoryIndex.of(
        Category(uuid5(NAMESPACE_URL, name), name, name.lower()) for name in CATEGORY_NAMES
    )


def category_id(name: str) -> object:
    return uuid5(NAMESPACE_URL, name)


def row(**overrides: str) -> list[str]:
    values = {
        "name": "Running Shoes",
        "sku": "RS-001",
        "description": "Lightweight running shoes",
        "category": "Footwear",
        "price": "89.99",
        "stock": "150",
        "weight_kg": "0.35",
    } | overrides
    return [values[column] for column in HEADER]


def csv_text(
    *rows: Sequence[str], header: Sequence[str] = HEADER, line_terminator: str = "\r\n"
) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator=line_terminator)
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue()


def run(
    content: str | bytes, index: CategoryIndex | None = None, max_problems: int = 10_000
) -> ImportAnalysis:
    data = content.encode() if isinstance(content, str) else content
    return analyze([data], index or categories(), max_problems)


def importable(content: str | bytes, analysis: ImportAnalysis) -> list[ImportableRow]:
    data = content.encode() if isinstance(content, str) else content
    return list(iter_importable_rows([data], categories(), analysis.winners))


def chunked(data: bytes, size: int) -> Iterable[bytes]:
    for start in range(0, len(data), size):
        yield data[start : start + size]


def errors(analysis: ImportAnalysis) -> list[Problem]:
    return [item for item in analysis.report.problems if item.severity is Severity.ERROR]


def warnings(analysis: ImportAnalysis) -> list[Problem]:
    return [item for item in analysis.report.problems if item.severity is Severity.WARNING]


def summary(analysis: ImportAnalysis) -> tuple[int, int, int, int, int, int]:
    report = analysis.report
    return (
        report.rows_read,
        report.blank_rows,
        report.error_rows,
        report.superseded_rows,
        report.duplicate_rows,
        report.importable_rows,
    )
