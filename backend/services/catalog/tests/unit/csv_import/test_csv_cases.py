from decimal import Decimal

import pytest
from catalog_testing.csv_import import (
    BLANK,
    category_id,
    csv_text,
    errors,
    importable,
    row,
    run,
    summary,
    warnings,
)

from catalog.domain.csv_import import Problem, Severity, UnknownCategory


def single(content: str) -> tuple[Problem, ...]:
    return run(content).report.problems


def test_blank_rows_are_ignored_and_not_counted_as_errors() -> None:
    content = csv_text(row(sku="A-1"), BLANK, BLANK, row(sku="A-2"))

    analysis = run(content)

    assert analysis.report.blank_rows == 2
    assert analysis.report.rows_read == 4
    assert analysis.report.problems == ()
    assert analysis.report.importable_rows == 2


@pytest.mark.parametrize(
    "blank_line",
    ["", "   ", ",,", " , ,  ,,,,", "\t,\t,,,,,"],
    ids=["empty-line", "spaces", "short-commas", "spaced-commas", "tabs"],
)
def test_every_flavour_of_blank_line_is_ignored(blank_line: str) -> None:
    content = csv_text(row()) + blank_line + "\r\n"

    analysis = run(content)

    assert analysis.report.blank_rows == 1
    assert analysis.report.problems == ()


def test_an_empty_name_is_an_error_with_row_column_value_and_reason() -> None:
    content = csv_text(row(sku="OK-1"), row(sku="HD-099", name=""))

    analysis = run(content)

    assert errors(analysis) == [
        Problem(Severity.ERROR, 3, "name", "", "required", "name must not be empty")
    ]
    assert analysis.report.importable_rows == 1


def test_a_name_with_only_spaces_is_an_error_and_keeps_the_received_value() -> None:
    analysis = run(csv_text(row(sku="WS-001", name="     ")))

    assert errors(analysis) == [
        Problem(Severity.ERROR, 2, "name", "     ", "required", "name must not be empty")
    ]


def test_a_price_with_a_currency_symbol_is_normalized_with_a_warning() -> None:
    content = csv_text(row(sku="WM-042", price="$29.99"))

    analysis = run(content)

    assert warnings(analysis) == [
        Problem(
            Severity.WARNING,
            2,
            "price",
            "$29.99",
            "price_normalized",
            "currency symbol removed, read as 29.99",
        )
    ]
    assert errors(analysis) == []
    assert importable(content, analysis)[0].product.data.price == Decimal("29.99")


def test_a_non_numeric_price_is_an_error() -> None:
    analysis = run(csv_text(row(sku="YM-015", price="free")))

    assert errors(analysis) == [
        Problem(
            Severity.ERROR,
            2,
            "price",
            "free",
            "not_a_number",
            "price must be a plain number such as 29.99",
        )
    ]
    assert analysis.report.importable_rows == 0


def test_a_zero_price_is_valid() -> None:
    content = csv_text(row(sku="MB-001", price="0.00"))

    analysis = run(content)

    assert analysis.report.problems == ()
    assert importable(content, analysis)[0].product.data.price == Decimal("0.00")


def test_a_negative_price_is_an_error() -> None:
    analysis = run(csv_text(row(price="-0.01")))

    assert errors(analysis) == [
        Problem(Severity.ERROR, 2, "price", "-0.01", "negative", "price must not be negative")
    ]


def test_a_negative_stock_is_an_error() -> None:
    analysis = run(csv_text(row(sku="DL-007", stock="-5")))

    assert errors(analysis) == [
        Problem(Severity.ERROR, 2, "stock", "-5", "negative", "stock must not be negative")
    ]


def test_a_zero_stock_is_valid() -> None:
    content = csv_text(row(sku="VC-001", stock="0"))

    analysis = run(content)

    assert analysis.report.problems == ()
    assert importable(content, analysis)[0].product.data.stock == 0


def test_a_very_high_stock_is_valid() -> None:
    content = csv_text(row(sku="GC-025", stock="99999"))

    analysis = run(content)

    assert analysis.report.problems == ()
    assert importable(content, analysis)[0].product.data.stock == 99999


def test_an_empty_weight_is_valid_and_stored_as_null() -> None:
    content = csv_text(row(sku="GK-088", weight_kg=""))

    analysis = run(content)

    assert analysis.report.problems == ()
    assert importable(content, analysis)[0].product.data.weight_kg is None


def test_a_zero_weight_is_valid() -> None:
    content = csv_text(row(sku="GC-025", weight_kg="0"))

    analysis = run(content)

    assert analysis.report.problems == ()
    assert importable(content, analysis)[0].product.data.weight_kg == Decimal("0.000")


def test_an_empty_category_is_valid_and_stored_as_null() -> None:
    content = csv_text(row(sku="GC-025", category=""))

    analysis = run(content)

    assert analysis.report.problems == ()
    assert importable(content, analysis)[0].product.data.category_id is None


def test_a_category_that_does_not_exist_is_an_error_with_a_suggestion() -> None:
    analysis = run(csv_text(row(category="Electornics")))

    assert errors(analysis) == [
        Problem(
            Severity.ERROR,
            2,
            "category",
            "Electornics",
            "unknown_category",
            "category does not exist and is not created automatically; did you mean Electronics?",
        )
    ]


def test_unknown_categories_are_grouped_with_the_number_of_rows_they_affect() -> None:
    content = csv_text(
        row(sku="A-1", category="Electornics"),
        row(sku="A-2", category=" ELECTORNICS "),
        row(sku="A-3", category="Home and Office"),
        row(sku="A-4", category="Zzzzzz"),
    )

    analysis = run(content)

    assert analysis.report.unknown_categories == (
        UnknownCategory("Electornics", 2, "Electronics"),
        UnknownCategory("Home and Office", 1, "Home & Office"),
        UnknownCategory("Zzzzzz", 1, None),
    )
    assert analysis.report.error_rows == 4


@pytest.mark.parametrize(
    ("written", "stored"),
    [
        ("electronics", "Electronics"),
        ("  Electronics  ", "Electronics"),
        ("FOOD & BEVERAGE", "Food & Beverage"),
        ("home   &    office", "Home & Office"),
        ("\tfootwear\t", "Footwear"),
    ],
)
def test_category_matching_ignores_case_and_surrounding_or_repeated_spaces(
    written: str, stored: str
) -> None:
    content = csv_text(row(category=written))

    analysis = run(content)

    assert analysis.report.problems == ()
    assert importable(content, analysis)[0].product.data.category_id == category_id(stored)


def test_a_repeated_sku_with_different_data_keeps_the_last_row_and_warns_about_the_first() -> None:
    content = csv_text(
        row(sku="RS-001", price="89.99", stock="150"),
        row(sku="OTHER-1"),
        row(sku="RS-001", price="94.99", stock="120"),
    )

    analysis = run(content)

    assert warnings(analysis) == [
        Problem(
            Severity.WARNING,
            2,
            "sku",
            "RS-001",
            "superseded",
            "replaced by row 4, the last row with this SKU",
        )
    ]
    winner = [item for item in importable(content, analysis) if item.product.sku == "RS-001"]
    assert [(item.row, item.product.data.price, item.product.data.stock) for item in winner] == [
        (4, Decimal("94.99"), 120)
    ]
    assert summary(analysis) == (3, 0, 0, 1, 0, 2)


def test_an_exact_duplicate_row_is_skipped_without_any_problem() -> None:
    content = csv_text(row(sku="BS-021"), row(sku="BS-021"))

    analysis = run(content)

    assert analysis.report.problems == ()
    assert summary(analysis) == (2, 0, 0, 0, 1, 1)


def test_a_row_identical_to_the_last_one_is_silent_and_the_different_one_in_between_warns() -> None:
    first = row(sku="BS-021", price="59.99", stock="110", weight_kg="0.8")
    different = row(sku="BS-021", price="49.99", stock="200", weight_kg="0.75")
    content = csv_text(first, different, first)

    analysis = run(content)

    assert warnings(analysis) == [
        Problem(
            Severity.WARNING,
            3,
            "sku",
            "BS-021",
            "superseded",
            "replaced by row 4, the last row with this SKU",
        )
    ]
    assert summary(analysis) == (3, 0, 0, 1, 1, 1)
    winner = importable(content, analysis)
    assert [(item.row, item.product.data.price) for item in winner] == [(4, Decimal("59.99"))]


def test_repeats_differing_only_by_spaces_or_case_of_the_sku_are_the_same_product() -> None:
    content = csv_text(row(sku="rs-001 ", price="1.00"), row(sku="RS-001", price="2.00"))

    analysis = run(content)

    assert summary(analysis) == (2, 0, 0, 1, 0, 1)


def test_when_the_last_row_for_a_sku_is_invalid_the_sku_is_not_imported() -> None:
    content = csv_text(row(sku="A-1"), row(sku="A-1", stock="-1"))

    analysis = run(content)

    assert [(item.code, item.row) for item in analysis.report.problems] == [
        ("superseded_by_invalid", 2),
        ("negative", 3),
    ]
    assert analysis.report.importable_rows == 0
    assert analysis.winners == {}
    assert summary(analysis) == (2, 0, 1, 1, 0, 0)


def test_an_invalid_row_followed_by_a_valid_one_for_the_same_sku_still_imports_the_valid_one() -> (
    None
):
    content = csv_text(row(sku="A-1", stock="-1"), row(sku="A-1", stock="5"))

    analysis = run(content)

    assert [item.code for item in analysis.report.problems] == ["negative"]
    assert analysis.winners == {"A-1": 3}
    assert summary(analysis) == (2, 0, 1, 0, 0, 1)


def test_the_same_name_with_different_skus_is_valid() -> None:
    content = csv_text(row(sku="RS-001"), row(sku="RS-050"))

    analysis = run(content)

    assert analysis.report.problems == ()
    assert analysis.report.importable_rows == 2


def test_html_in_a_name_is_kept_literally() -> None:
    name = "<script>alert('xss')</script>"
    content = csv_text(row(sku="XS-001", name=name))

    analysis = run(content)

    assert analysis.report.problems == ()
    assert importable(content, analysis)[0].product.data.name == name


def test_sql_looking_text_in_a_name_is_kept_literally() -> None:
    name = "Robert'); DROP TABLE products;--"
    content = csv_text(row(sku="SQL-001", name=name))

    analysis = run(content)

    assert analysis.report.problems == ()
    assert importable(content, analysis)[0].product.data.name == name


def test_commas_and_escaped_quotes_survive_parsing() -> None:
    content = csv_text(
        row(sku="CI-001", name="Comma, In Product Name"),
        row(sku="QI-001", name='Quote "Inside" Name'),
    )
    assert '"Quote ""Inside"" Name"' in content

    analysis = run(content)

    names = {item.product.sku: item.product.data.name for item in importable(content, analysis)}
    assert names == {"CI-001": "Comma, In Product Name", "QI-001": 'Quote "Inside" Name'}


def test_unicode_survives_parsing() -> None:
    description = "Stainless steel, 1L — keeps drinks cold for 24hrs™"
    content = csv_text(row(sku="WB-033", description=description))

    analysis = run(content)

    assert analysis.report.problems == ()
    assert importable(content, analysis)[0].product.data.description == description


def test_an_empty_description_is_stored_as_null() -> None:
    content = csv_text(row(description="   "))

    analysis = run(content)

    assert importable(content, analysis)[0].product.data.description is None


def test_a_lowercase_sku_is_uppercased_with_a_warning_but_spaces_are_trimmed_silently() -> None:
    content = csv_text(row(sku="rs-001"), row(sku="  RS-002  "))

    analysis = run(content)

    assert [(item.row, item.code, item.value) for item in warnings(analysis)] == [
        (2, "sku_uppercased", "rs-001")
    ]
    assert {item.product.sku for item in importable(content, analysis)} == {"RS-001", "RS-002"}


@pytest.mark.parametrize(
    ("overrides", "column", "code"),
    [
        ({"sku": ""}, "sku", "required"),
        ({"sku": "bad sku!"}, "sku", "invalid_sku"),
        ({"name": "x" * 256}, "name", "too_long"),
        ({"description": "x" * 5001}, "description", "too_long"),
        ({"price": "10000000000.00"}, "price", "too_large"),
        ({"price": "10.999"}, "price", "too_many_decimals"),
        ({"stock": "2147483648"}, "stock", "too_large"),
        ({"weight_kg": "1.2345"}, "weight_kg", "too_many_decimals"),
        ({"weight_kg": "-1"}, "weight_kg", "negative"),
        ({"weight_kg": "heavy"}, "weight_kg", "not_a_number"),
        ({"stock": "12.5"}, "stock", "not_an_integer"),
        ({"stock": ""}, "stock", "required"),
        ({"price": ""}, "price", "required"),
    ],
)
def test_each_column_rule_reports_the_column_and_the_received_value(
    overrides: dict[str, str], column: str, code: str
) -> None:
    analysis = run(csv_text(row(**overrides)))

    assert [(item.row, item.column, item.code) for item in errors(analysis)] == [(2, column, code)]
    sent = overrides[column]
    assert errors(analysis)[0].value == (sent if len(sent) <= 200 else sent[:199] + "…")


def test_every_problem_of_a_row_is_reported_not_only_the_first() -> None:
    analysis = run(csv_text(row(name="", price="free", stock="-1", category="Nope", weight_kg="x")))

    assert sorted(item.column or "" for item in errors(analysis)) == [
        "category",
        "name",
        "price",
        "stock",
        "weight_kg",
    ]
    assert analysis.report.error_rows == 1
    assert analysis.report.error_count == 5


def test_a_row_with_the_wrong_number_of_fields_is_an_error_and_is_not_padded() -> None:
    content = csv_text(row(sku="OK-1")) + "Short,ROW-1,desc\r\n"

    analysis = run(content)

    assert [(item.row, item.code, item.column) for item in errors(analysis)] == [
        (3, "column_count", None)
    ]
    assert errors(analysis)[0].reason == "expected 7 fields but found 3"


def test_a_row_with_extra_fields_is_an_error() -> None:
    content = csv_text([*row(sku="OK-1"), "surplus"])

    analysis = run(content)

    assert [item.code for item in errors(analysis)] == ["column_count"]


def test_long_received_values_are_truncated_in_the_report() -> None:
    analysis = run(csv_text(row(price="x" * 500)))

    value = errors(analysis)[0].value
    assert value is not None
    assert len(value) == 200
    assert value.endswith("…")


def test_the_row_count_identity_holds() -> None:
    content = csv_text(
        row(sku="A-1"),
        BLANK,
        row(sku="A-1", price="2.00"),
        row(sku="B-1", stock="-1"),
        row(sku="C-1"),
        row(sku="C-1"),
        row(sku="D-1"),
    )

    report = run(content).report

    assert report.rows_read == (
        report.blank_rows + report.error_rows + report.skipped_rows + report.importable_rows
    )
