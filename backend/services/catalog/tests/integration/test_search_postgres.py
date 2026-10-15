from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from catalog_testing.listing import BASE, Catalog, create_catalog
from catalog_testing.support import SEEDED_PRODUCT_COUNT
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.application.cursors import decode_cursor
from catalog.application.errors import SearchTimeoutError
from catalog.application.ports import UnitOfWorkFactory
from catalog.domain.listing import (
    Direction,
    PageRequest,
    Position,
    ProductFilters,
    Sort,
    TextMode,
)
from catalog.infra.database import create_engine, create_session_factory
from catalog.infra.explain import ExplainJson, parse_plan
from catalog.infra.search import build_search_statement, build_text_probe
from catalog.infra.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = pytest.mark.integration

FULL_SCAN_COST = 12_000


@pytest.fixture
async def catalog(migrated_database_url: str) -> AsyncIterator[Catalog]:
    engine = create_engine(migrated_database_url)
    factory = create_session_factory(engine)
    yield await create_catalog(lambda: SqlAlchemyUnitOfWork(factory))
    await engine.dispose()


@pytest.fixture
async def seeded_session(seeded_database_url: str) -> AsyncIterator[AsyncSession]:
    engine = create_engine(seeded_database_url)
    async with create_session_factory(engine)() as session:
        yield session
    await engine.dispose()


async def names_found(catalog: Catalog, query: str) -> list[str]:
    page = await catalog.service.search(
        ProductFilters(query=query, category=catalog.slug), None, 48, None
    )
    return [item.name for item in page.items]


async def test_a_typo_in_the_query_still_finds_the_product(catalog: Catalog) -> None:
    await catalog.add("Running Shoes", "Lightweight", Decimal("50.00"), 5, tick=0)
    await catalog.add("Coffee Mug", "Ceramic", Decimal("8.00"), 5, tick=1)
    await catalog.add("Trail Sandals", "Open toe", Decimal("30.00"), 5, tick=2)

    assert await names_found(catalog, "runing shoes") == ["Running Shoes"]
    assert await names_found(catalog, "running shose") == ["Running Shoes"]
    assert await names_found(catalog, "cofee mug") == ["Coffee Mug"]


async def test_a_typo_matches_inside_a_long_product_name(catalog: Catalog) -> None:
    long_name = "Lightweight Trail Running Shoes For Everyday Use"
    await catalog.add(long_name, None, Decimal("50.00"), 5, tick=0)

    assert await names_found(catalog, "runing shoes") == [long_name]


async def test_unrelated_queries_find_nothing(catalog: Catalog) -> None:
    await catalog.add("Running Shoes", "Lightweight", Decimal("50.00"), 5, tick=0)

    assert await names_found(catalog, "refrigerator") == []


async def test_typo_matches_appear_only_when_nothing_matches_exactly(catalog: Catalog) -> None:
    await catalog.add("Rinning Shoes Pro", None, Decimal("50.00"), 5, tick=1)
    await catalog.add("Running Shoes Classic", None, Decimal("50.00"), 5, tick=0)

    assert await names_found(catalog, "running shoes") == ["Running Shoes Classic"]
    assert (await names_found(catalog, "runing shoes"))[0] == "Running Shoes Classic"


async def test_the_typo_fallback_respects_the_other_filters(catalog: Catalog) -> None:
    await catalog.add("Running Shoes", None, Decimal("50.00"), 5, tick=0)
    await catalog.add("Rinning Shoes", None, Decimal("10.00"), 5, tick=1)
    filters = ProductFilters(query="running shoes", category=catalog.slug, max_price=Decimal("20"))

    page = await catalog.service.search(filters, None, 12, None)

    assert [item.name for item in page.items] == ["Rinning Shoes"]


async def test_stemming_matches_plural_and_verb_forms(catalog: Catalog) -> None:
    await catalog.add("Run Shoe", None, Decimal("50.00"), 5, tick=0)

    assert await names_found(catalog, "running shoes") == ["Run Shoe"]


async def test_the_description_and_the_sku_are_searchable(catalog: Catalog) -> None:
    product = await catalog.add("Plain Item", "Waterproof breathable fabric", Decimal("5.00"), 1, 0)

    assert await names_found(catalog, "waterproof") == ["Plain Item"]
    assert await names_found(catalog, product.sku) == ["Plain Item"]


async def test_name_matches_outrank_description_matches(catalog: Catalog) -> None:
    await catalog.add("Garden Hose", "A great lantern holder", Decimal("5.00"), 1, 0)
    await catalog.add("Lantern", "Camping light", Decimal("5.00"), 1, 1)

    assert await names_found(catalog, "lantern") == ["Lantern", "Garden Hose"]


@pytest.mark.parametrize("query", ["'", "&", "a | b", '"unterminated', "!!", "((", "100%", "\\"])
async def test_hostile_query_text_never_breaks_the_search(catalog: Catalog, query: str) -> None:
    await catalog.add("Running Shoes", None, Decimal("50.00"), 5, tick=0)

    page = await catalog.service.search(ProductFilters(query=query), None, 12, None)

    assert page.total.value >= 0


async def test_the_total_is_exact_when_few_products_match(
    seeded_database_url: str,
) -> None:
    engine = create_engine(seeded_database_url)
    try:
        async with SqlAlchemyUnitOfWork(create_session_factory(engine)) as uow:
            filters = ProductFilters(category="books", max_price=Decimal("1.50"))
            total = await uow.products.count(filters, None)
            real = (await uow.products.search(filters, Sort.NEWEST, PageRequest(1000))).rows
    finally:
        await engine.dispose()

    assert total.exact
    assert total.value == len(real)


async def test_the_total_is_a_close_estimate_when_many_products_match(
    seeded_session: AsyncSession,
) -> None:
    uow = SqlAlchemyUnitOfWork(create_session_factory(seeded_session.bind))  # type: ignore[arg-type]
    async with uow:
        everything = await uow.products.count(ProductFilters(), None)
        in_stock = await uow.products.count(ProductFilters(in_stock=True), None)
    real = await seeded_session.scalar(
        text("SELECT count(*) FROM products WHERE deleted_at IS NULL")
    )
    real_in_stock = await seeded_session.scalar(
        text("SELECT count(*) FROM products WHERE deleted_at IS NULL AND stock > 0")
    )

    assert not everything.exact
    assert not in_stock.exact
    assert abs(everything.value - (real or 0)) <= 0.05 * (real or 0)
    assert abs(in_stock.value - (real_in_stock or 0)) <= 0.05 * (real_in_stock or 0)


def plan_nodes(plan: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = [plan]
    for child in plan.get("Plans", []):
        nodes.extend(plan_nodes(child))
    return nodes


async def explain(
    session: AsyncSession,
    filters: ProductFilters,
    sort: Sort,
    page: PageRequest | None = None,
    mode: TextMode = TextMode.FULL_TEXT,
) -> list[dict[str, Any]]:
    statement = build_search_statement(filters, sort, page or PageRequest(24), mode)
    raw = await session.scalar(ExplainJson(statement))
    return plan_nodes(parse_plan(raw))


def node_types(nodes: list[dict[str, Any]]) -> set[str]:
    return {node["Node Type"] for node in nodes}


def scans_the_whole_products_table(nodes: list[dict[str, Any]]) -> bool:
    return any(
        node["Node Type"] == "Seq Scan" and node["Relation Name"] == "products" for node in nodes
    )


def index_names(nodes: list[dict[str, Any]]) -> set[str]:
    return {node["Index Name"] for node in nodes if "Index Name" in node}


async def test_the_seeded_table_is_big_enough_for_plans_to_matter(
    seeded_session: AsyncSession,
) -> None:
    count = await seeded_session.scalar(text("SELECT count(*) FROM products"))

    assert count == SEEDED_PRODUCT_COUNT


@pytest.mark.parametrize("query", ["running shoes", "nordwind running shoes", "zephyr m17"])
async def test_full_text_search_uses_the_gin_index(
    seeded_session: AsyncSession, query: str
) -> None:
    nodes = await explain(seeded_session, ProductFilters(query=query), Sort.RELEVANCE)

    assert "ix_products_search_vector" in index_names(nodes)
    assert not scans_the_whole_products_table(nodes)


async def test_the_existence_probe_is_cheap_whatever_the_query(
    seeded_session: AsyncSession,
) -> None:
    for query in ("running shoes", "zephyr m17", "refrigerator"):
        raw = await seeded_session.scalar(
            ExplainJson(build_text_probe(ProductFilters(query=query)))
        )
        plan = parse_plan(raw)

        assert plan["Total Cost"] < FULL_SCAN_COST / 10, query


@pytest.mark.parametrize("query", ["zefyr", "zephir m17"])
async def test_selective_typo_searches_use_the_trigram_index(
    seeded_session: AsyncSession, query: str
) -> None:
    nodes = await explain(
        seeded_session, ProductFilters(query=query), Sort.RELEVANCE, mode=TextMode.TRIGRAM
    )

    assert "ix_products_name_trgm" in index_names(nodes)
    assert not scans_the_whole_products_table(nodes)


@pytest.mark.parametrize(
    ("sort", "index"),
    [
        (Sort.NEWEST, "ix_products_created_at_id"),
        (Sort.PRICE_ASC, "ix_products_price_id"),
        (Sort.PRICE_DESC, "ix_products_price_id"),
    ],
)
async def test_browsing_walks_the_sort_index_without_sorting(
    seeded_session: AsyncSession, sort: Sort, index: str
) -> None:
    nodes = await explain(seeded_session, ProductFilters(), sort)

    assert index in index_names(nodes)
    assert not {"Sort", "Incremental Sort"} & node_types(nodes)
    assert not scans_the_whole_products_table(nodes)


@pytest.mark.parametrize(
    ("sort", "index", "key"),
    [
        (Sort.NEWEST, "ix_products_created_at_id", datetime(2025, 3, 1, tzinfo=UTC)),
        (Sort.PRICE_ASC, "ix_products_price_id", Decimal("250.00")),
        (Sort.PRICE_DESC, "ix_products_price_id", Decimal("250.00")),
    ],
)
@pytest.mark.parametrize("direction", list(Direction))
async def test_deep_pages_in_either_direction_still_use_the_index(
    seeded_session: AsyncSession,
    sort: Sort,
    index: str,
    key: datetime | Decimal,
    direction: Direction,
) -> None:
    page = PageRequest(24, direction, Position(key, uuid4()))

    nodes = await explain(seeded_session, ProductFilters(), sort, page)

    assert index in index_names(nodes)
    assert not {"Sort", "Incremental Sort"} & node_types(nodes)
    assert not scans_the_whole_products_table(nodes)


async def test_filters_never_fall_back_to_a_sequential_scan(seeded_session: AsyncSession) -> None:
    combinations = [
        ProductFilters(category="books"),
        ProductFilters(category="books", in_stock=True),
        ProductFilters(min_price=Decimal("100.00"), max_price=Decimal("120.00")),
        ProductFilters(query="desk lamp", category="home-office", max_price=Decimal("300.00")),
    ]

    for filters in combinations:
        for sort in (Sort.NEWEST, Sort.PRICE_ASC, Sort.PRICE_DESC):
            nodes = await explain(seeded_session, filters, sort)
            assert not scans_the_whole_products_table(nodes), (filters, sort)


async def test_the_search_returns_results_on_the_seeded_table(
    seeded_database_url: str,
) -> None:
    engine = create_engine(seeded_database_url)
    factory: UnitOfWorkFactory = lambda: SqlAlchemyUnitOfWork(create_session_factory(engine))  # noqa: E731
    try:
        async with factory() as uow:
            exact = (
                await uow.products.search(
                    ProductFilters(query="running shoes"), Sort.RELEVANCE, PageRequest(24)
                )
            ).rows
            typo = (
                await uow.products.search(
                    ProductFilters(query="runing shoes"), Sort.RELEVANCE, PageRequest(24)
                )
            ).rows
    finally:
        await engine.dispose()

    assert len(exact) > 24
    assert len(typo) > 24
    assert all("shoe" in row.product.name.lower() for row in typo[:24])


async def test_the_migration_runs_as_a_plain_database_owner_without_superuser_rights(
    create_owned_database: Callable[[str, str], str],
    alembic_runner: Callable[[str, str, str], None],
) -> None:
    url = create_owned_database("catalog_owner", "owner-secret")
    alembic_runner(url, "upgrade", "head")

    engine = create_engine(url)
    try:
        async with engine.connect() as connection:
            superuser = await connection.scalar(
                text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
            )
            extension = await connection.scalar(
                text("SELECT extname FROM pg_extension WHERE extname = 'pg_trgm'")
            )
    finally:
        await engine.dispose()

    assert make_url(url).username == "catalog_owner"
    assert superuser is False
    assert extension == "pg_trgm"


async def test_a_walk_keeps_its_trigram_mode_when_an_exact_match_appears_midway(
    catalog: Catalog,
) -> None:
    for index in range(14):
        await catalog.add("Rinning Shoes", None, Decimal("50.00"), 5, tick=index)
    filters = ProductFilters(query="running shoes", category=catalog.slug)
    fingerprint = filters.fingerprint(Sort.NEWEST)

    first = await catalog.service.search(filters, Sort.NEWEST, 5, None)
    assert first.next_cursor is not None
    assert decode_cursor(first.next_cursor, Sort.NEWEST, fingerprint).mode is TextMode.TRIGRAM
    await catalog.add("Running Shoes", None, Decimal("50.00"), 5, tick=100)
    walked = [first]
    while walked[-1].next_cursor is not None:
        walked.append(await catalog.service.search(filters, Sort.NEWEST, 5, walked[-1].next_cursor))

    names = [item.name for page in walked for item in page.items]
    ids_seen = [item.id for page in walked for item in page.items]
    assert names == ["Rinning Shoes"] * 14
    assert len(ids_seen) == len(set(ids_seen))
    assert first.total.value == 14
    assert all(page.total.value == 15 for page in walked[1:])

    back = await catalog.service.search(filters, Sort.NEWEST, 5, walked[1].prev_cursor)
    assert [item.id for item in back.items] == [item.id for item in first.items]

    restarted = await catalog.service.search(filters, Sort.NEWEST, 5, None)
    assert next(item.name for item in restarted.items) == "Running Shoes"
    assert restarted.total.value == 1


async def test_a_walk_keeps_its_full_text_mode_when_the_exact_matches_disappear_midway(
    catalog: Catalog,
) -> None:
    for index in range(12):
        await catalog.add("Running Shoes", None, Decimal("50.00"), 5, tick=index)
    for index in range(6):
        await catalog.add("Rinning Shoes", None, Decimal("50.00"), 5, tick=index)
    exact_skus = [item.sku for item in catalog.products if item.name == "Running Shoes"]
    filters = ProductFilters(query="running shoes", category=catalog.slug)

    first = await catalog.service.search(filters, Sort.NEWEST, 5, None)
    assert {item.name for item in first.items} == {"Running Shoes"}
    async with catalog.unit_of_work() as uow:
        for sku in exact_skus:
            await uow.products.soft_delete(sku, BASE)
        await uow.commit()

    second = await catalog.service.search(filters, Sort.NEWEST, 5, first.next_cursor)

    assert second.items == []
    assert second.total.value == 0
    restarted = await catalog.service.search(filters, Sort.NEWEST, 5, None)
    assert {item.name for item in restarted.items} == {"Rinning Shoes"}


async def test_a_slow_search_is_cancelled_by_the_statement_timeout(
    seeded_database_url: str,
) -> None:
    engine = create_engine(seeded_database_url)
    factory = create_session_factory(engine)
    try:
        async with SqlAlchemyUnitOfWork(factory, search_timeout_ms=1) as uow:
            with pytest.raises(SearchTimeoutError) as raised:
                await uow.products.search(
                    ProductFilters(query="refrigerator freezer"), Sort.RELEVANCE, PageRequest(24)
                )
    finally:
        await engine.dispose()

    assert raised.value.timeout_ms == 1


async def test_a_generous_timeout_lets_the_search_through_and_does_not_outlive_it(
    seeded_database_url: str,
) -> None:
    engine = create_engine(seeded_database_url)
    factory = create_session_factory(engine)
    try:
        async with SqlAlchemyUnitOfWork(factory, search_timeout_ms=5000) as uow:
            result = await uow.products.search(
                ProductFilters(query="zephyr m17"), Sort.RELEVANCE, PageRequest(24)
            )
            await uow.products.count(ProductFilters(query="zephyr m17"), result.mode)
        async with factory() as session:
            leftover = await session.scalar(text("SHOW statement_timeout"))
    finally:
        await engine.dispose()

    assert result.rows
    assert leftover == "0"


async def test_the_timeout_leaves_other_statements_unbounded(seeded_database_url: str) -> None:
    engine = create_engine(seeded_database_url)
    factory = create_session_factory(engine)
    try:
        async with SqlAlchemyUnitOfWork(factory, search_timeout_ms=1) as uow:
            with pytest.raises(SearchTimeoutError):
                await uow.products.search(
                    ProductFilters(query="refrigerator freezer"), Sort.RELEVANCE, PageRequest(24)
                )
        async with factory() as session:
            slow = await session.scalar(
                text("SELECT count(*) FROM products WHERE name ILIKE '%e%'")
            )
    finally:
        await engine.dispose()

    assert slow is not None
    assert slow > 0
