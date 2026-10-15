from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Final

from catalog.domain.csv_import.categories import CategoryIndex
from catalog.domain.csv_import.dedup import Occurrence, resolve_repeats
from catalog.domain.csv_import.document import Header, RawRecord, Rejection, read_document
from catalog.domain.csv_import.problems import Problem, Severity
from catalog.domain.csv_import.report import ImportReport, UnknownCategory
from catalog.domain.csv_import.rows import BlankRow, InvalidRow, RowOutcome, ValidRow, evaluate_row
from catalog.domain.product import NewProduct

DEFAULT_MAX_PROBLEMS: Final = 10_000


@dataclass(frozen=True, slots=True)
class ImportAnalysis:
    report: ImportReport
    winners: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class ImportableRow:
    row: int
    product: NewProduct


def _scan(chunks: Iterable[bytes], categories: CategoryIndex) -> Iterator[RowOutcome | Rejection]:
    columns: tuple[str, ...] = ()
    for event in read_document(chunks):
        match event:
            case Header(found):
                columns = found
            case RawRecord(row, fields):
                yield evaluate_row(row, fields, columns, categories)
            case Rejection():
                yield event


def analyze(
    chunks: Iterable[bytes],
    categories: CategoryIndex,
    max_problems: int = DEFAULT_MAX_PROBLEMS,
) -> ImportAnalysis:
    rows_read = blank_rows = error_rows = 0
    errors: list[Problem] = []
    warnings: list[Problem] = []
    error_count = warning_count = 0
    latest: dict[str, Occurrence] = {}
    earlier: dict[str, list[Occurrence]] = {}
    unknown_rows: Counter[str] = Counter()
    unknown_label: dict[str, str] = {}

    def note(problem: Problem) -> None:
        nonlocal error_count, warning_count
        if problem.severity is Severity.ERROR:
            error_count += 1
            if len(errors) < max_problems:
                errors.append(problem)
        else:
            warning_count += 1
            if len(warnings) < max_problems:
                warnings.append(problem)

    def track(sku: str, occurrence: Occurrence) -> None:
        previous = latest.get(sku)
        if previous is not None and previous.valid:
            earlier.setdefault(sku, []).append(previous)
        latest[sku] = occurrence

    for outcome in _scan(chunks, categories):
        match outcome:
            case Rejection(problems):
                report = ImportReport(
                    rejected=True,
                    rows_read=rows_read,
                    blank_rows=blank_rows,
                    error_count=len(problems),
                    problems=problems[:max_problems],
                    truncated=len(problems) > max_problems,
                )
                return ImportAnalysis(report, {})
            case BlankRow():
                rows_read += 1
                blank_rows += 1
            case InvalidRow(row, sku, problems, unknown):
                rows_read += 1
                error_rows += 1
                for problem in problems:
                    note(problem)
                if unknown is not None:
                    key = " ".join(unknown.split()).casefold()
                    unknown_rows[key] += 1
                    unknown_label.setdefault(key, " ".join(unknown.split()))
                if sku is not None:
                    track(sku, Occurrence(row, None))
            case ValidRow(row, product, digest, row_warnings):
                rows_read += 1
                for problem in row_warnings:
                    note(problem)
                track(product.sku, Occurrence(row, digest))

    duplicates = superseded = 0
    for sku, previous in earlier.items():
        resolution = resolve_repeats(sku, previous, latest[sku])
        duplicates += resolution.duplicates
        superseded += resolution.superseded
        for problem in resolution.warnings:
            note(problem)

    winners = {sku: found.row for sku, found in latest.items() if found.valid}
    report = ImportReport(
        rejected=False,
        rows_read=rows_read,
        blank_rows=blank_rows,
        error_rows=error_rows,
        superseded_rows=superseded,
        duplicate_rows=duplicates,
        importable_rows=len(winners),
        error_count=error_count,
        warning_count=warning_count,
        problems=tuple(sorted((*errors, *warnings), key=_problem_order)),
        truncated=error_count > len(errors) or warning_count > len(warnings),
        unknown_categories=_group_unknown(unknown_rows, unknown_label, categories),
    )
    return ImportAnalysis(report, winners)


def iter_importable_rows(
    chunks: Iterable[bytes], categories: CategoryIndex, winners: Mapping[str, int]
) -> Iterator[ImportableRow]:
    for outcome in _scan(chunks, categories):
        if isinstance(outcome, ValidRow) and winners.get(outcome.product.sku) == outcome.row:
            yield ImportableRow(outcome.row, outcome.product)


def _problem_order(problem: Problem) -> tuple[int, int]:
    return (problem.row or 0, 0 if problem.severity is Severity.ERROR else 1)


def _group_unknown(
    rows: Counter[str], labels: Mapping[str, str], categories: CategoryIndex
) -> tuple[UnknownCategory, ...]:
    grouped = [
        UnknownCategory(labels[key], count, categories.suggest(labels[key]))
        for key, count in rows.items()
    ]
    return tuple(sorted(grouped, key=lambda item: (-item.rows, item.value)))
