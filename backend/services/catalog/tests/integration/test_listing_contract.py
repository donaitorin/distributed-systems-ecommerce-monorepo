from datetime import timedelta
from decimal import Decimal
from itertools import pairwise
from uuid import uuid4

import pytest
from catalog_testing.listing import BASE, SORTS, Catalog, create_catalog, fill_with_ties

from catalog.application.ports import UnitOfWorkFactory
from catalog.domain.listing import (
    Direction,
    PageRequest,
    Position,
    ProductFilters,
    ProductListing,
    Sort,
)
from catalog.domain.product import Product


@pytest.fixture
async def catalog(unit_of_work: UnitOfWorkFactory) -> Catalog:
    return await create_catalog(unit_of_work)


def ids(pages: list[ProductListing]) -> list[object]:
    return [item.id for page in pages for item in page.items]


def expected_order(products: list[Product], sort: Sort) -> list[object]:
    match sort:
        case Sort.NEWEST:
            ordered = sorted(products, key=lambda item: (item.created_at, item.id), reverse=True)
        case Sort.PRICE_ASC:
            ordered = sorted(products, key=lambda item: (item.price, item.id))
        case _:
            ordered = sorted(products, key=lambda item: (item.price, item.id), reverse=True)
    return [item.id for item in ordered]


@pytest.mark.parametrize("sort", SORTS)
@pytest.mark.parametrize("limit", [5, 12])
async def test_walking_forward_visits_every_product_once_in_order(
    catalog: Catalog, sort: Sort, limit: int
) -> None:
    await fill_with_ties(catalog)

    pages = await catalog.walk(sort, limit)

    visited = ids(pages)
    assert len(visited) == len(set(visited)) == 53
    assert visited == expected_order(catalog.products, sort)
    assert pages[0].prev_cursor is None
    assert pages[-1].next_cursor is None
    assert all(len(page.items) == limit for page in pages[:-1])


@pytest.mark.parametrize("sort", SORTS)
async def test_walking_backward_returns_the_same_pages_in_reverse(
    catalog: Catalog, sort: Sort
) -> None:
    await fill_with_ties(catalog)
    forward = await catalog.walk(sort, 8)

    backward = await catalog.walk_back(forward[-1], sort, 8)

    assert [ids([page]) for page in backward] == [ids([page]) for page in reversed(forward)]
    assert backward[-1].prev_cursor is None


async def test_a_previous_page_always_links_forward_again(catalog: Catalog) -> None:
    await fill_with_ties(catalog, 20)
    first = await catalog.service.search(catalog.filters, Sort.NEWEST, 8, None)
    second = await catalog.service.search(catalog.filters, Sort.NEWEST, 8, first.next_cursor)

    back_to_first = await catalog.service.search(
        catalog.filters, Sort.NEWEST, 8, second.prev_cursor
    )

    assert ids([back_to_first]) == ids([first])
    assert back_to_first.next_cursor is not None
    assert back_to_first.prev_cursor is None


async def test_a_page_that_fits_everything_has_no_cursors(catalog: Catalog) -> None:
    await fill_with_ties(catalog, 5)

    page = await catalog.service.search(catalog.filters, None, 12, None)

    assert len(page.items) == 5
    assert (page.next_cursor, page.prev_cursor) == (None, None)


async def test_new_products_inserted_while_paging_do_not_shift_the_pages(catalog: Catalog) -> None:
    await fill_with_ties(catalog, 20)
    first = await catalog.service.search(catalog.filters, Sort.NEWEST, 8, None)
    await catalog.add("Late arrival", None, Decimal("1.00"), 1, tick=500)

    second = await catalog.service.search(catalog.filters, Sort.NEWEST, 8, first.next_cursor)

    assert not set(ids([first])) & set(ids([second]))
    assert ids([first, second]) == expected_order(catalog.products[:-1], Sort.NEWEST)[:16]


async def test_soft_deleted_products_are_left_out_of_pages_and_totals(catalog: Catalog) -> None:
    await fill_with_ties(catalog, 10)
    removed = catalog.products[3]
    async with catalog.unit_of_work() as uow:
        await uow.products.soft_delete(removed.sku, BASE)
        await uow.commit()

    pages = await catalog.walk(Sort.NEWEST, 4)

    assert removed.id not in ids(pages)
    assert len(ids(pages)) == 9
    assert pages[0].total.value == 9


async def test_the_total_is_exact_for_small_result_sets(catalog: Catalog) -> None:
    await fill_with_ties(catalog, 17)

    page = await catalog.service.search(catalog.filters, None, 12, None)

    assert (page.total.value, page.total.exact) == (17, True)


async def test_price_filters_are_inclusive_and_combine(catalog: Catalog) -> None:
    await fill_with_ties(catalog)
    filters = ProductFilters(
        category=catalog.slug, min_price=Decimal("20.00"), max_price=Decimal("35.50")
    )

    pages = await catalog.walk(Sort.PRICE_ASC, 12, filters)

    wanted = [
        item for item in catalog.products if Decimal("20.00") <= item.price <= Decimal("35.50")
    ]
    assert ids(pages) == expected_order(wanted, Sort.PRICE_ASC)
    assert pages[0].total.value == len(wanted)


async def test_in_stock_hides_sold_out_products(catalog: Catalog) -> None:
    await fill_with_ties(catalog)
    filters = ProductFilters(category=catalog.slug, in_stock=True)

    pages = await catalog.walk(Sort.NEWEST, 12, filters)

    wanted = [item for item in catalog.products if item.stock > 0]
    assert ids(pages) == expected_order(wanted, Sort.NEWEST)


async def test_every_filter_together_with_a_price_sort(catalog: Catalog) -> None:
    await fill_with_ties(catalog)
    filters = ProductFilters(
        category=catalog.slug,
        min_price=Decimal("10.00"),
        max_price=Decimal("50.00"),
        in_stock=True,
    )

    pages = await catalog.walk(Sort.PRICE_DESC, 5, filters)

    wanted = [
        item
        for item in catalog.products
        if Decimal("10.00") <= item.price <= Decimal("50.00") and item.stock > 0
    ]
    assert ids(pages) == expected_order(wanted, Sort.PRICE_DESC)


async def test_an_unknown_category_slug_yields_an_empty_page(catalog: Catalog) -> None:
    await fill_with_ties(catalog, 5)

    page = await catalog.service.search(ProductFilters(category="no-such-slug"), None, 12, None)

    assert page.items == []
    assert (page.total.value, page.total.exact) == (0, True)
    assert (page.next_cursor, page.prev_cursor) == (None, None)


async def test_a_text_query_narrows_the_walk_to_matching_products(catalog: Catalog) -> None:
    for index in range(9):
        await catalog.add("Running Shoes", "Lightweight", Decimal("50.00"), 5, tick=index)
    for index in range(7):
        await catalog.add("Coffee Mug", "Ceramic", Decimal("8.00"), 5, tick=index)
    filters = ProductFilters(query="running shoes", category=catalog.slug)

    pages = await catalog.walk(Sort.NEWEST, 4, filters)

    matching = [item.id for item in catalog.products if item.name == "Running Shoes"]
    assert sorted(ids(pages), key=str) == sorted(matching, key=str)
    assert pages[0].total.value == 9


async def test_equal_relevance_scores_survive_the_cursor_round_trip(catalog: Catalog) -> None:
    for index in range(24):
        await catalog.add("Running Shoes", "Lightweight", Decimal("50.00"), 5, tick=index)
    for index in range(8):
        await catalog.add("Trail Running Shoes", "Lightweight", Decimal("60.00"), 5, tick=index)
    for index in range(5):
        await catalog.add("Running Shoes Pro", "Carbon plate", Decimal("120.00"), 5, tick=index)
    filters = ProductFilters(query="running shoes", category=catalog.slug)
    async with catalog.unit_of_work() as uow:
        everything = (await uow.products.search(filters, Sort.RELEVANCE, PageRequest(1000))).rows
    scores = [row.score for row in everything]
    reference = [row.product.id for row in everything]
    first_tie = next(index for index in range(1, len(scores)) if scores[index] == scores[index - 1])
    assert scores == sorted(scores, reverse=True)  # type: ignore[type-var]
    assert len(set(scores)) < len(scores)

    for limit in (first_tie, 7, 11):
        pages = await catalog.walk(Sort.RELEVANCE, limit, filters)
        boundary_scores = [
            (
                scores[reference.index(page.items[-1].id)],
                scores[reference.index(page.items[-1].id) + 1],
            )
            for page in pages[:-1]
        ]
        assert ids(pages) == reference
        assert len(ids(pages)) == len(set(ids(pages))) == len(reference)
        if limit == first_tie:
            assert boundary_scores[0][0] == boundary_scores[0][1]

    tied = [
        (previous, current)
        for previous, current in pairwise(everything)
        if previous.score == current.score
    ]
    assert tied
    assert all(previous.product.id > current.product.id for previous, current in tied)

    last = (await catalog.walk(Sort.RELEVANCE, first_tie, filters))[-1]
    backward = await catalog.walk_back(last, Sort.RELEVANCE, first_tie, filters)
    assert [item for page in reversed(backward) for item in ids([page])] == reference


async def test_the_default_sort_with_a_query_is_relevance(catalog: Catalog) -> None:
    await catalog.add("Coffee Mug With Running Shoes Print", None, Decimal("8.00"), 5, tick=1)
    await catalog.add("Running Shoes", None, Decimal("50.00"), 5, tick=0)
    filters = ProductFilters(query="running shoes", category=catalog.slug)

    page = await catalog.service.search(filters, None, 12, None)

    assert page.items[0].name == "Running Shoes"


async def test_a_position_beyond_the_last_product_gives_an_empty_page(catalog: Catalog) -> None:
    await fill_with_ties(catalog, 5)
    async with catalog.unit_of_work() as uow:
        result = await uow.products.search(
            catalog.filters,
            Sort.NEWEST,
            PageRequest(5, Direction.AFTER, Position(BASE - timedelta(days=1), uuid4())),
        )

    assert result.rows == []
