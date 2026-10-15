from decimal import Decimal

from catalog_testing.csv_import import SAMPLE_FILE, categories, category_id, summary
from catalog_testing.csv_import import errors as errors_of
from catalog_testing.csv_import import warnings as warnings_of

from catalog.domain.csv_import import Problem, Severity, analyze, iter_importable_rows

DATA = SAMPLE_FILE.read_bytes()
ANALYSIS = analyze([DATA], categories())
IMPORTED = {
    item.product.sku: item for item in iter_importable_rows([DATA], categories(), ANALYSIS.winners)
}


def test_the_sample_file_is_what_the_spec_describes() -> None:
    assert DATA.startswith(b"name,sku,description,category,price,stock,weight_kg\r\n")
    assert not DATA.startswith(b"\xef\xbb\xbf")
    assert len(DATA.splitlines()) == 98


def test_the_whole_sample_file_gives_the_expected_report() -> None:
    report = ANALYSIS.report

    assert not report.rejected
    assert report.rows_read == 97
    assert report.blank_rows == 2
    assert report.error_rows == 4
    assert report.error_count == 4
    assert report.warning_count == 3
    assert report.superseded_rows == 2
    assert report.duplicate_rows == 1
    assert report.importable_rows == 88
    assert report.unknown_categories == ()
    assert not report.truncated


def test_the_sample_file_has_exactly_these_four_errors() -> None:
    assert errors_of(ANALYSIS) == [
        Problem(
            Severity.ERROR,
            7,
            "price",
            "free",
            "not_a_number",
            "price must be a plain number such as 29.99",
        ),
        Problem(Severity.ERROR, 16, "stock", "-5", "negative", "stock must not be negative"),
        Problem(Severity.ERROR, 25, "name", "", "required", "name must not be empty"),
        Problem(Severity.ERROR, 41, "name", "     ", "required", "name must not be empty"),
    ]


def test_the_sample_file_has_exactly_these_three_warnings() -> None:
    assert warnings_of(ANALYSIS) == [
        Problem(
            Severity.WARNING,
            2,
            "sku",
            "RS-001",
            "superseded",
            "replaced by row 36, the last row with this SKU",
        ),
        Problem(
            Severity.WARNING,
            4,
            "price",
            "$29.99",
            "price_normalized",
            "currency symbol removed, read as 29.99",
        ),
        Problem(
            Severity.WARNING,
            56,
            "sku",
            "BS-021",
            "superseded",
            "replaced by row 89, the last row with this SKU",
        ),
    ]


def test_the_row_numbers_are_the_spreadsheet_rows_of_the_file() -> None:
    lines = DATA.decode().splitlines()

    assert lines[6].startswith("Yoga Mat,YM-015")
    assert ",free," in lines[6]
    assert lines[15].startswith("Desk Lamp,DL-007")
    assert ",-5," in lines[15]
    assert lines[24].startswith(",HD-099")
    assert lines[40].startswith("     ,WS-001")
    assert lines[61] == ",,,,,,"
    assert lines[62] == ",,,,,,"
    assert lines[1].startswith("Running Shoes,RS-001")
    assert lines[35].startswith("Running Shoes,RS-001")
    assert lines[10] == lines[88]


def test_the_four_invalid_skus_are_not_imported_and_the_rest_are() -> None:
    assert {"YM-015", "DL-007", "HD-099", "WS-001"}.isdisjoint(IMPORTED)
    assert len(IMPORTED) == 88
    assert len(ANALYSIS.winners) == 88


def test_rs_001_keeps_the_last_row() -> None:
    winner = IMPORTED["RS-001"]

    assert winner.row == 36
    assert winner.product.data.price == Decimal("94.99")
    assert winner.product.data.stock == 120
    assert winner.product.data.description == (
        "Updated lightweight shoes — now with better arch support"
    )


def test_bs_021_keeps_the_last_row_which_equals_the_first_and_skips_the_different_one() -> None:
    winner = IMPORTED["BS-021"]

    assert winner.row == 89
    assert winner.product.data.price == Decimal("59.99")
    assert winner.product.data.stock == 110
    assert winner.product.data.weight_kg == Decimal("0.800")
    assert winner.product.data.description == "Portable waterproof speaker, 10W, 12hr battery"


def test_the_same_name_with_different_skus_is_kept_for_both() -> None:
    assert IMPORTED["RS-050"].product.data.name == IMPORTED["RS-001"].product.data.name
    assert IMPORTED["BS-099"].product.data.name == IMPORTED["BS-021"].product.data.name


def test_the_html_name_is_stored_literally() -> None:
    assert IMPORTED["XS-001"].product.data.name == "<script>alert('xss')</script>"


def test_the_sql_injection_name_is_stored_literally() -> None:
    assert IMPORTED["SQL-001"].product.data.name == "Robert'); DROP TABLE products;--"


def test_the_price_with_a_currency_symbol_is_stored_as_a_number() -> None:
    assert IMPORTED["WM-042"].product.data.price == Decimal("29.99")


def test_the_zero_price_product_is_valid() -> None:
    assert IMPORTED["MB-001"].product.data.price == Decimal("0.00")


def test_the_zero_stock_and_the_huge_stock_are_valid() -> None:
    assert IMPORTED["VC-001"].product.data.stock == 0
    assert IMPORTED["GC-025"].product.data.stock == 99999


def test_the_empty_weight_is_null_and_the_zero_weight_is_zero() -> None:
    assert IMPORTED["GK-088"].product.data.weight_kg is None
    assert IMPORTED["GC-025"].product.data.weight_kg == Decimal("0.000")


def test_the_empty_category_is_null_and_the_others_are_resolved() -> None:
    assert IMPORTED["GC-025"].product.data.category_id is None
    assert IMPORTED["RS-001"].product.data.category_id == category_id("Footwear")
    assert IMPORTED["CB-010"].product.data.category_id == category_id("Food & Beverage")
    assert IMPORTED["WS-001" if False else "MB-001"].product.data.category_id == category_id(
        "Gifts"
    )


def test_commas_quotes_and_unicode_survive() -> None:
    assert IMPORTED["CI-001"].product.data.name == "Comma, In Product Name"
    assert IMPORTED["QI-001"].product.data.name == 'Quote "Inside" Name'
    assert IMPORTED["WB-033"].product.data.description == (
        "Stainless steel, 1L — keeps drinks cold for 24hrs™"
    )
    assert IMPORTED["CB-010"].product.data.description == "Single origin, medium roast, 1kg bag"


def test_every_row_is_accounted_for() -> None:
    report = ANALYSIS.report

    assert report.rows_read == (
        report.blank_rows + report.error_rows + report.skipped_rows + report.importable_rows
    )
    assert summary(ANALYSIS) == (97, 2, 4, 2, 1, 88)


def test_every_imported_product_has_a_category_except_the_gift_card() -> None:
    without_category = {
        sku for sku, item in IMPORTED.items() if item.product.data.category_id is None
    }

    assert without_category == {"GC-025"}
