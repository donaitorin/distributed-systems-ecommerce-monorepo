from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from catalog_testing.support import SEEDED_CATEGORIES

from catalog.application.errors import (
    DuplicateCategoryError,
    DuplicateSkuError,
    UnknownCategoryError,
)
from catalog.application.ports import UnitOfWorkFactory
from catalog.domain.product import NewProduct, ProductData
from catalog.infra.database import create_engine, create_session_factory
from catalog.infra.memory import InMemoryStore, InMemoryUnitOfWork
from catalog.infra.unit_of_work import SqlAlchemyUnitOfWork

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


@pytest.fixture(
    params=["memory", pytest.param("sql", marks=pytest.mark.integration)],
)
async def unit_of_work(request: pytest.FixtureRequest) -> AsyncIterator[UnitOfWorkFactory]:
    if request.param == "memory":
        store = InMemoryStore()
        store.seed_categories(*SEEDED_CATEGORIES)
        yield lambda: InMemoryUnitOfWork(store)
        return
    url: str = request.getfixturevalue("migrated_database_url")
    engine = create_engine(url)
    session_factory = create_session_factory(engine)
    yield lambda: SqlAlchemyUnitOfWork(session_factory)
    await engine.dispose()


def unique_sku() -> str:
    return f"T{uuid4().hex[:12].upper()}"


def new_product(sku: str | None = None, **overrides: object) -> NewProduct:
    values: dict[str, object] = {
        "name": "Running Shoes",
        "description": "Light",
        "category_id": None,
        "price": Decimal("89.99"),
        "stock": 10,
        "weight_kg": Decimal("0.350"),
    }
    return NewProduct(sku=sku or unique_sku(), data=ProductData(**(values | overrides)))  # type: ignore[arg-type]


async def books_category_id(unit_of_work: UnitOfWorkFactory) -> object:
    async with unit_of_work() as uow:
        categories = await uow.categories.list_all()
    return next(item.id for item in categories if item.slug == "books")


async def test_added_products_can_be_read_back_with_exact_values(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    candidate = new_product()
    async with unit_of_work() as uow:
        added = await uow.products.add(candidate, NOW)
        await uow.commit()

    async with unit_of_work() as uow:
        stored = await uow.products.get(candidate.sku)

    assert stored == added
    assert stored is not None
    assert stored.version == 1
    assert stored.price == Decimal("89.99")
    assert stored.weight_kg == Decimal("0.350")
    assert stored.created_at == stored.updated_at == NOW
    assert stored.category is None


async def test_uncommitted_work_is_discarded(unit_of_work: UnitOfWorkFactory) -> None:
    candidate = new_product()
    async with unit_of_work() as uow:
        await uow.products.add(candidate, NOW)

    async with unit_of_work() as uow:
        assert await uow.products.get(candidate.sku) is None


async def test_the_category_is_joined_into_the_product(unit_of_work: UnitOfWorkFactory) -> None:
    category_id = await books_category_id(unit_of_work)
    candidate = new_product(category_id=category_id)
    async with unit_of_work() as uow:
        await uow.products.add(candidate, NOW)
        await uow.commit()

    async with unit_of_work() as uow:
        stored = await uow.products.get(candidate.sku)

    assert stored is not None
    assert stored.category is not None
    assert stored.category.slug == "books"


async def test_duplicate_sku_is_reported(unit_of_work: UnitOfWorkFactory) -> None:
    candidate = new_product()
    async with unit_of_work() as uow:
        await uow.products.add(candidate, NOW)
        await uow.commit()

    async with unit_of_work() as uow:
        with pytest.raises(DuplicateSkuError):
            await uow.products.add(new_product(candidate.sku, name="Other"), NOW)


async def test_unknown_category_is_reported_on_add(unit_of_work: UnitOfWorkFactory) -> None:
    async with unit_of_work() as uow:
        with pytest.raises(UnknownCategoryError):
            await uow.products.add(new_product(category_id=uuid4()), NOW)


async def test_replace_changes_the_fields_and_increments_the_version(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    candidate = new_product()
    later = NOW + timedelta(minutes=5)
    async with unit_of_work() as uow:
        await uow.products.add(candidate, NOW)
        await uow.commit()

    async with unit_of_work() as uow:
        replaced = await uow.products.replace(
            candidate.sku,
            ProductData("Trail", None, None, Decimal("12.50"), 0, None),
            later,
        )
        await uow.commit()

    async with unit_of_work() as uow:
        stored = await uow.products.get(candidate.sku)

    assert stored == replaced
    assert stored is not None
    assert (stored.name, stored.description, stored.stock, stored.weight_kg) == (
        "Trail",
        None,
        0,
        None,
    )
    assert stored.price == Decimal("12.50")
    assert stored.version == 2
    assert stored.created_at == NOW
    assert stored.updated_at == later


async def test_soft_deleted_products_disappear_but_keep_their_sku(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    candidate = new_product()
    async with unit_of_work() as uow:
        await uow.products.add(candidate, NOW)
        await uow.commit()

    async with unit_of_work() as uow:
        await uow.products.soft_delete(candidate.sku, NOW)
        await uow.commit()

    async with unit_of_work() as uow:
        assert await uow.products.get(candidate.sku) is None
        assert await uow.products.get_for_update(candidate.sku) is None
        assert candidate.sku not in [item.sku for item in await uow.products.list(1000)]
        with pytest.raises(DuplicateSkuError):
            await uow.products.add(new_product(candidate.sku), NOW)


async def test_list_is_ordered_by_sku_and_limited(unit_of_work: UnitOfWorkFactory) -> None:
    prefix = unique_sku()
    skus = [f"{prefix}-{letter}" for letter in "CAB"]
    async with unit_of_work() as uow:
        for sku in skus:
            await uow.products.add(new_product(sku), NOW)
        await uow.commit()

    async with unit_of_work() as uow:
        listed = [item.sku for item in await uow.products.list(1000) if item.sku.startswith(prefix)]
        first_page = await uow.products.list(1)

    assert listed == sorted(skus)
    assert len(first_page) == 1


async def test_categories_are_listed_added_and_unique(unit_of_work: UnitOfWorkFactory) -> None:
    name = f"Cat {uuid4().hex[:8]}"
    async with unit_of_work() as uow:
        created = await uow.categories.add(name, name.lower().replace(" ", "-"))
        await uow.commit()

    async with unit_of_work() as uow:
        assert await uow.categories.get(created.id) == created
        assert created in await uow.categories.list_all()
        with pytest.raises(DuplicateCategoryError):
            await uow.categories.add(name.upper(), "another-slug-" + uuid4().hex[:6])
    async with unit_of_work() as uow:
        with pytest.raises(DuplicateCategoryError):
            await uow.categories.add("Different Name " + uuid4().hex[:6], created.slug)


async def test_unknown_category_lookup_returns_none(unit_of_work: UnitOfWorkFactory) -> None:
    async with unit_of_work() as uow:
        assert await uow.categories.get(uuid4()) is None
