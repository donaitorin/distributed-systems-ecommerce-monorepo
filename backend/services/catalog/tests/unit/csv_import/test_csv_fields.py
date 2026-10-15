from decimal import Decimal

import pytest

from catalog.domain.csv_import.fields import parse_price, parse_stock, parse_weight


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10", "10"),
        ("10.5", "10.5"),
        ("29.99", "29.99"),
        (".5", "0.5"),
        ("5.", "5"),
        ("0", "0"),
        ("0.00", "0.00"),
        ("+7.25", "7.25"),
        ("  12.00  ", "12.00"),
        ("-3", "-3"),
    ],
)
def test_plain_numbers_are_accepted_as_prices(raw: str, expected: str) -> None:
    parsed = parse_price(raw, 2)

    assert parsed.value == Decimal(expected)
    assert parsed.problems == ()


@pytest.mark.parametrize("raw", ["$29.99", "$ 29.99", " $29.99 ", "$0", "$.5"])
def test_a_leading_dollar_sign_is_removed_with_a_warning(raw: str) -> None:
    parsed = parse_price(raw, 7)

    assert parsed.value is not None
    assert [(item.severity.value, item.code, item.row, item.value) for item in parsed.problems] == [
        ("warning", "price_normalized", 7, raw)
    ]


@pytest.mark.parametrize(
    "raw",
    [
        "free",
        "N/A",
        "1,299.99",
        "29,99",
        "1e3",
        "1_000",
        "NaN",
        "Infinity",
        "-inf",
        "12$",
        "$$12",
        "€12",
        "USD 12",
        "12 USD",
        "1 2",
        "0x10",
        "--5",
        "$",
        "$free",
        "٣",
        "\uff11\uff12",
    ],
)
def test_anything_that_is_not_a_plain_number_is_a_price_error(raw: str) -> None:
    parsed = parse_price(raw, 3)

    assert parsed.value is None
    assert parsed.failed
    assert parsed.problems[0].code in {"not_a_number", "required"}
    assert parsed.problems[0].value == raw


@pytest.mark.parametrize("raw", ["", "   "])
def test_an_empty_price_is_required(raw: str) -> None:
    parsed = parse_price(raw, 3)

    assert [item.code for item in parsed.problems] == ["required"]


@pytest.mark.parametrize(
    ("raw", "expected"), [("0", 0), ("5", 5), (" 150 ", 150), ("+3", 3), ("-5", -5), ("007", 7)]
)
def test_whole_numbers_are_accepted_as_stock(raw: str, expected: int) -> None:
    parsed = parse_stock(raw, 2)

    assert parsed.value == expected
    assert parsed.problems == ()


@pytest.mark.parametrize(
    "raw", ["12.0", "12.5", "1,000", "ten", "1e3", "1_0", "NaN", "", "  ", "5 0", "٣"]
)
def test_stock_that_is_not_a_whole_number_is_an_error(raw: str) -> None:
    parsed = parse_stock(raw, 2)

    assert parsed.value is None
    assert parsed.failed


def test_an_absurdly_long_stock_is_an_error_not_a_crash() -> None:
    parsed = parse_stock("9" * 10_000, 2)

    assert parsed.failed
    assert parsed.problems[0].reason == "stock has too many digits"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("", None), ("   ", None), ("0", "0"), ("1.0", "1.0"), ("0.350", "0.350"), (".5", "0.5")],
)
def test_weight_is_optional_and_otherwise_a_plain_number(raw: str, expected: str | None) -> None:
    parsed = parse_weight(raw, 2)

    assert parsed.value == (Decimal(expected) if expected is not None else None)
    assert parsed.problems == ()
    assert not parsed.failed


@pytest.mark.parametrize("raw", ["heavy", "1,5", "1kg", "NaN", "$3"])
def test_a_weight_that_is_not_a_number_is_an_error(raw: str) -> None:
    parsed = parse_weight(raw, 2)

    assert parsed.failed
    assert parsed.problems[0].column == "weight_kg"
