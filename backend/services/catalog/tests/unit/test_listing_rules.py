from decimal import Decimal

import pytest

from catalog.domain.listing import ProductFilters, Sort, build_filters, resolve_sort


def test_filters_are_normalized() -> None:
    filters = build_filters("  running   shoes ", " Footwear ", Decimal("5"), Decimal("20.5"), True)

    assert filters == ProductFilters(
        "running shoes", "footwear", Decimal("5.00"), Decimal("20.50"), True
    )


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_a_blank_query_or_category_means_no_filter(blank: str | None) -> None:
    assert build_filters(blank, blank, None, None, None) == ProductFilters()


def test_in_stock_false_is_the_same_as_omitting_it() -> None:
    assert build_filters(None, None, None, None, False) == build_filters(
        None, None, None, None, None
    )


@pytest.mark.parametrize(
    ("requested", "query", "expected"),
    [
        (None, "shoes", Sort.RELEVANCE),
        (None, None, Sort.NEWEST),
        (Sort.RELEVANCE, None, Sort.NEWEST),
        (Sort.RELEVANCE, "shoes", Sort.RELEVANCE),
        (Sort.PRICE_ASC, "shoes", Sort.PRICE_ASC),
        (Sort.PRICE_DESC, None, Sort.PRICE_DESC),
        (Sort.NEWEST, "shoes", Sort.NEWEST),
    ],
)
def test_the_effective_sort(requested: Sort | None, query: str | None, expected: Sort) -> None:
    assert resolve_sort(requested, ProductFilters(query=query)) is expected


def test_the_fingerprint_changes_with_any_filter_or_the_sort() -> None:
    base = ProductFilters(query="shoes")
    variants = [
        base.fingerprint(Sort.NEWEST),
        base.fingerprint(Sort.PRICE_ASC),
        ProductFilters(query="boots").fingerprint(Sort.NEWEST),
        ProductFilters(query="shoes", category="footwear").fingerprint(Sort.NEWEST),
        ProductFilters(query="shoes", min_price=Decimal("1.00")).fingerprint(Sort.NEWEST),
        ProductFilters(query="shoes", max_price=Decimal("1.00")).fingerprint(Sort.NEWEST),
        ProductFilters(query="shoes", in_stock=True).fingerprint(Sort.NEWEST),
    ]

    assert len(set(variants)) == len(variants)
    assert base.fingerprint(Sort.NEWEST) == ProductFilters(query="shoes").fingerprint(Sort.NEWEST)
