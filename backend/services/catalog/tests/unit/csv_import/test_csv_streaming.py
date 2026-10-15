from collections.abc import Iterator
from decimal import Decimal

import pytest
from catalog_testing.csv_import import (
    BLANK,
    SAMPLE_FILE,
    categories,
    chunked,
    csv_text,
    row,
    run,
)

from catalog.domain.csv_import import analyze, iter_importable_rows

SAMPLE = SAMPLE_FILE.read_bytes()


@pytest.mark.parametrize("size", [1, 2, 3, 7, 64, 1000, len(SAMPLE)])
def test_the_report_does_not_depend_on_how_the_bytes_are_chunked(size: int) -> None:
    whole = analyze([SAMPLE], categories())

    pieces = analyze(chunked(SAMPLE, size), categories())

    assert pieces == whole


@pytest.mark.parametrize("size", [1, 2, 5])
def test_a_byte_order_mark_and_multibyte_characters_split_across_chunks_are_handled(
    size: int,
) -> None:
    data = b"\xef\xbb\xbf" + csv_text(row(description="Cold — 24hrs™ ✓", name="Café")).encode()

    analysis = analyze(chunked(data, size), categories())
    imported = list(iter_importable_rows(chunked(data, size), categories(), analysis.winners))

    assert analysis.report.problems == ()
    assert imported[0].product.data.description == "Cold — 24hrs™ ✓"
    assert imported[0].product.data.name == "Café"


def test_unix_and_windows_line_endings_give_the_same_report() -> None:
    windows = analyze([SAMPLE], categories())
    unix = analyze([SAMPLE.replace(b"\r\n", b"\n")], categories())

    assert unix == windows


def test_a_byte_order_mark_does_not_change_the_report() -> None:
    plain = analyze([SAMPLE], categories())
    marked = analyze([b"\xef\xbb\xbf" + SAMPLE], categories())

    assert marked == plain


class CountingChunks:
    def __init__(self, data: bytes, size: int) -> None:
        self._data = data
        self._size = size
        self.pulled = 0
        self.total = -(-len(data) // size)

    def __iter__(self) -> Iterator[bytes]:
        for chunk in chunked(self._data, self._size):
            self.pulled += 1
            yield chunk


def test_a_file_rejected_by_its_header_is_not_read_any_further() -> None:
    data = b"colour,size\r\n" + b"red,10\r\n" * 5_000
    chunks = CountingChunks(data, 100)

    analysis = analyze(chunks, categories())

    assert analysis.report.rejected
    assert chunks.pulled < chunks.total / 10


def test_the_importable_rows_are_produced_lazily() -> None:
    data = csv_text(*(row(sku=f"S-{number}") for number in range(2_000))).encode()
    chunks = CountingChunks(data, 200)
    winners = {f"S-{number}": number + 2 for number in range(2_000)}

    first = next(iter(iter_importable_rows(chunks, categories(), winners)))

    assert first.product.sku == "S-0"
    assert chunks.pulled < chunks.total / 10


def test_a_large_file_is_processed_in_one_pass() -> None:
    rows = [row(sku=f"S-{number}", name=f"Product {number}") for number in range(20_000)]
    data = csv_text(*rows).encode()

    analysis = analyze(chunked(data, 8_192), categories())

    assert analysis.report.rows_read == 20_000
    assert analysis.report.importable_rows == 20_000
    assert analysis.report.problems == ()


def test_the_number_of_stored_problems_is_capped_but_the_counts_stay_exact() -> None:
    content = csv_text(*(row(sku=f"S-{number}", name="") for number in range(50)))

    report = run(content, max_problems=10).report

    assert report.error_count == 50
    assert report.error_rows == 50
    assert len(report.problems) == 10
    assert report.truncated


def test_warnings_and_errors_are_capped_separately_so_errors_are_not_crowded_out() -> None:
    content = csv_text(
        *(row(sku=f"W-{number}", price="$5") for number in range(30)),
        row(sku="E-1", name=""),
    )

    report = run(content, max_problems=5).report

    assert report.warning_count == 30
    assert report.error_count == 1
    assert [item.severity.value for item in report.problems].count("error") == 1
    assert [item.severity.value for item in report.problems].count("warning") == 5
    assert report.truncated


def test_a_report_within_the_cap_is_not_truncated() -> None:
    report = run(csv_text(row(name=""))).report

    assert not report.truncated


def test_a_truncated_rejection_keeps_its_document_problems_within_the_cap() -> None:
    header = ",".join(f"unknown{number}" for number in range(20)) + "\r\n"

    report = run(header, max_problems=5).report

    assert report.rejected
    assert len(report.problems) == 5
    assert report.error_count == 24
    assert report.truncated


def test_problems_are_ordered_by_row_with_errors_before_warnings_on_the_same_row() -> None:
    content = csv_text(
        row(sku="A-1", price="$5"),
        row(sku="B-1", name=""),
        row(sku="A-1", price="$6"),
    )

    problems = run(content).report.problems

    assert [(item.row, item.severity.value) for item in problems] == [
        (2, "warning"),
        (2, "warning"),
        (3, "error"),
        (4, "warning"),
    ]


def test_only_the_winning_rows_are_produced_in_file_order() -> None:
    content = csv_text(
        row(sku="A-1", price="1.00"),
        row(sku="B-1", stock="-1"),
        BLANK,
        row(sku="C-1"),
        row(sku="A-1", price="2.00"),
    )
    analysis = run(content)

    produced = list(iter_importable_rows([content.encode()], categories(), analysis.winners))

    assert [(item.row, item.product.sku) for item in produced] == [(5, "C-1"), (6, "A-1")]
    assert produced[1].product.data.price == Decimal("2.00")


def test_nothing_is_produced_for_a_rejected_file() -> None:
    assert list(iter_importable_rows([b"colour\r\nred\r\n"], categories(), {"A": 2})) == []


def test_rows_not_in_the_winners_map_are_never_produced() -> None:
    content = csv_text(row(sku="A-1"), row(sku="B-1")).encode()

    produced = list(iter_importable_rows([content], categories(), {"B-1": 3}))

    assert [item.product.sku for item in produced] == ["B-1"]
