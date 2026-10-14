from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest

from catalog.domain.errors import ValidationFailedError
from catalog.domain.product import (
    DESCRIPTION_MAX_LENGTH,
    NAME_MAX_LENGTH,
    PRICE_MAX,
    STOCK_MAX,
    WEIGHT_MAX,
    build_new_product,
    build_product_data,
    normalize_sku,
)


def fields(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "name": "Running Shoes",
        "description": "Lightweight",
        "category_id": None,
        "price": Decimal("89.99"),
        "stock": 150,
        "weight_kg": Decimal("0.35"),
    }
    return base | overrides


def violations_for(**overrides: Any) -> dict[str, str]:
    with pytest.raises(ValidationFailedError) as raised:
        build_product_data(**fields(**overrides))
    return {item.location: item.code for item in raised.value.violations}


def test_valid_data_is_accepted_and_normalized() -> None:
    category_id = uuid4()

    data = build_product_data(
        **fields(
            name="  Running Shoes  ",
            description="  Light  ",
            category_id=category_id,
            price=Decimal("89.9"),
            weight_kg=Decimal("0.35"),
        )
    )

    assert data.name == "Running Shoes"
    assert data.description == "Light"
    assert data.category_id == category_id
    assert data.price == Decimal("89.90")
    assert str(data.price) == "89.90"
    assert str(data.weight_kg) == "0.350"


@pytest.mark.parametrize("description", [None, "", "   "])
def test_blank_description_becomes_null(description: str | None) -> None:
    data = build_product_data(**fields(description=description))

    assert data.description is None


def test_weight_is_optional() -> None:
    data = build_product_data(**fields(weight_kg=None))

    assert data.weight_kg is None


@pytest.mark.parametrize("price", [Decimal("0"), Decimal("0.00"), PRICE_MAX, Decimal("0.01")])
def test_price_boundaries_are_valid(price: Decimal) -> None:
    assert build_product_data(**fields(price=price)).price == price.quantize(Decimal("0.01"))


@pytest.mark.parametrize(
    ("price", "code"),
    [
        (Decimal("-0.01"), "negative"),
        (Decimal("-1"), "negative"),
        (Decimal("1.234"), "too_many_decimals"),
        (Decimal("0.001"), "too_many_decimals"),
        (PRICE_MAX + Decimal("0.01"), "too_large"),
        (Decimal("NaN"), "not_finite"),
        (Decimal("Infinity"), "not_finite"),
    ],
)
def test_invalid_prices_are_rejected(price: Decimal, code: str) -> None:
    assert violations_for(price=price) == {"price": code}


@pytest.mark.parametrize("stock", [0, 1, 99999, STOCK_MAX])
def test_stock_boundaries_are_valid(stock: int) -> None:
    assert build_product_data(**fields(stock=stock)).stock == stock


@pytest.mark.parametrize(("stock", "code"), [(-1, "negative"), (STOCK_MAX + 1, "too_large")])
def test_invalid_stock_is_rejected(stock: int, code: str) -> None:
    assert violations_for(stock=stock) == {"stock": code}


@pytest.mark.parametrize("weight", [Decimal("0"), Decimal("0.001"), WEIGHT_MAX])
def test_weight_boundaries_are_valid(weight: Decimal) -> None:
    assert build_product_data(**fields(weight_kg=weight)).weight_kg is not None


@pytest.mark.parametrize(
    ("weight", "code"),
    [
        (Decimal("-0.1"), "negative"),
        (Decimal("0.0001"), "too_many_decimals"),
        (WEIGHT_MAX + Decimal("0.001"), "too_large"),
    ],
)
def test_invalid_weight_is_rejected(weight: Decimal, code: str) -> None:
    assert violations_for(weight_kg=weight) == {"weight_kg": code}


@pytest.mark.parametrize("name", ["", "   ", "\t\n"])
def test_blank_name_is_rejected(name: str) -> None:
    assert violations_for(name=name) == {"name": "required"}


def test_name_length_limit_applies_after_trimming() -> None:
    assert build_product_data(**fields(name=f" {'x' * NAME_MAX_LENGTH} ")).name == "x" * 255
    assert violations_for(name="x" * (NAME_MAX_LENGTH + 1)) == {"name": "too_long"}


def test_description_length_limit() -> None:
    assert violations_for(description="x" * (DESCRIPTION_MAX_LENGTH + 1)) == {
        "description": "too_long"
    }


@pytest.mark.parametrize(
    "name",
    [
        "<script>alert('xss')</script>",
        "Robert'); DROP TABLE products;--",
        'Quote "Inside" Name',
        "Comma, In Product Name",
        "Water Bottle — 1L™",
    ],
)
def test_hostile_and_unicode_names_are_kept_literally(name: str) -> None:
    assert build_product_data(**fields(name=name)).name == name


def test_every_violation_is_reported_together() -> None:
    result = violations_for(name=" ", price=Decimal("-1"), stock=-5, weight_kg=Decimal("-2"))

    assert result == {
        "name": "required",
        "price": "negative",
        "stock": "negative",
        "weight_kg": "negative",
    }


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("RS-001", "RS-001"),
        ("  rs-001 ", "RS-001"),
        ("a", "A"),
        ("0-9._-x", "0-9._-X"),
        ("X" * 64, "X" * 64),
    ],
)
def test_sku_is_trimmed_and_uppercased(raw: str, expected: str) -> None:
    assert normalize_sku(raw) == expected


@pytest.mark.parametrize(
    "raw", ["", "  ", "-starts-with-hyphen", "has space", "a/b", "ñandú", "X" * 65, "a;b"]
)
def test_malformed_sku_is_rejected(raw: str) -> None:
    assert normalize_sku(raw) is None


def test_new_product_reports_sku_and_field_problems_together() -> None:
    with pytest.raises(ValidationFailedError) as raised:
        build_new_product("bad sku", **fields(price=Decimal("-1")))

    assert {item.location: item.code for item in raised.value.violations} == {
        "sku": "invalid_sku",
        "price": "negative",
    }


def test_new_product_carries_the_normalized_sku() -> None:
    new_product = build_new_product("rs-001", **fields())

    assert new_product.sku == "RS-001"
    assert new_product.data.name == "Running Shoes"
