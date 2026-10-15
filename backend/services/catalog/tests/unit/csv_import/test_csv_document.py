import pytest
from catalog_testing.csv_import import HEADER, categories, csv_text, errors, importable, row, run

from catalog.domain.csv_import import Problem, Severity, analyze


def codes(content: str | bytes) -> list[tuple[str, str | None]]:
    return [(item.code, item.column) for item in run(content).report.problems]


@pytest.mark.parametrize(
    "content",
    [b"", b"   ", b"\r\n\r\n", b"\xef\xbb\xbf", b" \n \n"],
    ids=["zero-bytes", "spaces", "blank-lines", "bom-only", "whitespace-lines"],
)
def test_an_empty_file_is_rejected(content: bytes) -> None:
    analysis = run(content)

    assert analysis.report.rejected
    assert analysis.report.problems == (
        Problem(Severity.ERROR, None, None, None, "empty_file", "the file is empty"),
    )
    assert analysis.winners == {}


def test_a_file_with_only_a_header_is_rejected_for_having_no_rows() -> None:
    analysis = run(csv_text())

    assert analysis.report.rejected
    assert [item.code for item in analysis.report.problems] == ["no_rows"]


def test_a_file_with_a_header_and_only_blank_rows_is_rejected_for_having_no_rows() -> None:
    analysis = run(csv_text(["", "", "", "", "", "", ""], ["", "", "", "", "", "", ""]))

    assert analysis.report.rejected
    assert [item.code for item in analysis.report.problems] == ["no_rows"]
    assert analysis.report.blank_rows == 2


def test_binary_content_is_rejected_as_not_text() -> None:
    png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + bytes(range(256))

    analysis = run(png)

    assert analysis.report.rejected
    assert [item.code for item in analysis.report.problems] == ["not_text"]


def test_a_nul_byte_inside_otherwise_valid_text_is_rejected_as_not_text() -> None:
    assert [code for code, _ in codes(csv_text(row()).encode() + b"\x00")] == ["not_text"]


def test_a_file_that_is_not_utf8_is_rejected_with_the_position() -> None:
    content = csv_text(row(name="Café")).encode("latin-1")

    analysis = run(content)

    assert analysis.report.rejected
    problem = analysis.report.problems[0]
    assert problem.code == "invalid_encoding"
    assert problem.reason.startswith("the file is not valid UTF-8 (invalid byte near position")


@pytest.mark.parametrize("encoding", ["utf-16", "utf-16-le", "utf-16-be"])
def test_a_utf16_file_gets_a_specific_hint(encoding: str) -> None:
    content = ("﻿" + csv_text(row())).encode(encoding)
    content = content if encoding == "utf-16" else b"\xff\xfe" + content

    problem = run(content).report.problems[0]

    assert problem.code in {"invalid_encoding", "not_text"}


def test_a_utf16_byte_order_mark_is_explained() -> None:
    content = b"\xff\xfe" + "name,sku\r\n".encode("utf-16-le").replace(b"\x00", b"\xe9")

    problem = run(content).report.problems[0]

    assert problem.code == "invalid_encoding"
    assert problem.reason == "the file looks UTF-16 encoded; save it as UTF-8"


def test_a_file_that_ends_in_the_middle_of_a_multibyte_character_is_rejected() -> None:
    content = csv_text(row()).encode() + "—".encode()[:2]

    assert [code for code, _ in codes(content)] == ["invalid_encoding"]


def test_a_utf8_byte_order_mark_is_accepted_and_removed() -> None:
    content = b"\xef\xbb\xbf" + csv_text(row()).encode()

    analysis = run(content)

    assert not analysis.report.rejected
    assert analysis.report.problems == ()
    assert importable(content, analysis)[0].product.sku == "RS-001"


def test_all_missing_required_columns_are_reported_at_once() -> None:
    analysis = run("description,category\r\nx,y\r\n")

    assert analysis.report.rejected
    assert [(item.code, item.column) for item in analysis.report.problems] == [
        ("missing_column", "name"),
        ("missing_column", "sku"),
        ("missing_column", "price"),
        ("missing_column", "stock"),
    ]
    assert all(item.row == 1 for item in analysis.report.problems)


def test_unknown_columns_are_reported_with_the_allowed_ones() -> None:
    analysis = run(csv_text(header=(*HEADER, "colour", "Brand")))

    assert analysis.report.rejected
    assert [(item.code, item.column) for item in analysis.report.problems] == [
        ("unknown_column", "colour"),
        ("unknown_column", "Brand"),
    ]
    assert "allowed columns are name, sku, price, stock, description, category, weight_kg" in (
        analysis.report.problems[0].reason
    )


def test_duplicate_columns_are_reported() -> None:
    header = ("name", "sku", "price", "stock", "Name")

    analysis = run(csv_text(header=header))

    assert [(item.code, item.column) for item in analysis.report.problems] == [
        ("duplicate_column", "Name")
    ]


def test_missing_unknown_and_duplicate_columns_are_all_reported_together() -> None:
    analysis = run("name,sku,sku,flavour\r\n")

    assert sorted(item.code for item in analysis.report.problems) == [
        "duplicate_column",
        "missing_column",
        "missing_column",
        "unknown_column",
    ]


def test_header_names_ignore_case_and_surrounding_spaces() -> None:
    content = "  NAME , Sku ,Price,STOCK\r\nShoes,rs-1,10,5\r\n"

    analysis = run(content)

    assert not analysis.report.rejected
    assert [item.code for item in analysis.report.problems] == ["sku_uppercased"]
    assert analysis.report.importable_rows == 1


def test_optional_columns_may_be_absent() -> None:
    content = "name,sku,price,stock\r\nShoes,RS-1,10,5\r\n"

    analysis = run(content)

    product = importable(content, analysis)[0].product
    assert analysis.report.problems == ()
    assert (product.data.description, product.data.category_id, product.data.weight_kg) == (
        None,
        None,
        None,
    )


def test_columns_may_come_in_any_order() -> None:
    content = "stock,price,sku,name\r\n5,10,RS-1,Shoes\r\n"

    analysis = run(content)

    product = importable(content, analysis)[0].product
    assert (product.sku, product.data.name, product.data.stock) == ("RS-1", "Shoes", 5)


@pytest.mark.parametrize(("separator", "label"), [(";", "semicolon"), ("\t", "tab"), ("|", "pipe")])
def test_a_file_with_another_separator_gets_a_hint(separator: str, label: str) -> None:
    content = separator.join(HEADER) + "\r\n"

    problems = run(content).report.problems

    assert problems[0].code == "unknown_column"
    assert problems[0].reason == f"the columns look {label}-separated; use commas"


@pytest.mark.parametrize(
    "content",
    [
        'name,sku,price,stock\r\n"unterminated,RS-1,10,5\r\n',
        'name,sku,price,stock\r\n"Shoes"x,RS-1,10,5\r\n',
    ],
    ids=["unclosed-quote", "text-after-quote"],
)
def test_a_malformed_csv_is_rejected_as_a_whole_with_the_row(content: str) -> None:
    analysis = run(content)

    assert analysis.report.rejected
    assert [(item.code, item.row) for item in analysis.report.problems] == [("malformed_csv", 2)]
    assert analysis.report.problems[0].reason.startswith("not a valid CSV")


def test_a_lone_carriage_return_inside_an_unquoted_field_is_rejected() -> None:
    assert [code for code, _ in codes("name,sku,price,stock\rShoes,RS-1,10,5\r")] == [
        "malformed_csv"
    ]


def test_a_field_larger_than_the_csv_limit_is_rejected() -> None:
    content = csv_text(row(description="x" * 200_000))

    assert [code for code, _ in codes(content)] == ["malformed_csv"]


def test_leading_blank_lines_before_the_header_are_skipped_and_rows_keep_their_position() -> None:
    content = "\r\n\r\nname,sku,price,stock\r\nShoes,RS-1,-1,5\r\n"

    analysis = run(content)

    assert [(item.row, item.column) for item in errors(analysis)] == [(4, "price")]


def test_a_header_problem_reports_the_actual_header_row() -> None:
    analysis = run("\r\nname,sku\r\n")

    assert {item.row for item in analysis.report.problems} == {2}


def test_a_quoted_field_with_a_line_break_counts_as_one_row() -> None:
    content = csv_text(
        row(sku="A-1", description="first line\r\nsecond line"),
        row(sku="B-1", stock="-1"),
    )

    analysis = run(content)

    assert [(item.row, item.column) for item in errors(analysis)] == [(3, "stock")]
    assert importable(content, analysis)[0].product.data.description == (
        "first line\r\nsecond line"
    )


@pytest.mark.parametrize("terminator", ["\r\n", "\n"])
def test_both_line_endings_are_accepted(terminator: str) -> None:
    content = csv_text(row(sku="A-1"), row(sku="B-1"), line_terminator=terminator)

    analysis = run(content)

    assert analysis.report.problems == ()
    assert analysis.report.rows_read == 2


def test_a_missing_final_newline_does_not_lose_the_last_row() -> None:
    content = csv_text(row(sku="A-1"), row(sku="B-1")).rstrip()

    assert run(content).report.importable_rows == 2


def test_rejected_files_report_how_many_rows_were_read_before_the_failure() -> None:
    good = csv_text(row(sku="A-1"), row(sku="A-2")).encode()

    report = analyze([good, b"\xff\xfe"], categories()).report

    assert report.rejected
    assert report.rows_read == 2
    assert report.error_count == 1


def test_a_rejection_reports_no_importable_rows_even_if_earlier_rows_were_fine() -> None:
    content = csv_text(row(sku="A-1")).encode() + b"\xff"

    analysis = run(content)

    assert analysis.report.importable_rows == 0
    assert analysis.winners == {}
