from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.infra.database import create_engine, create_session_factory
from catalog.infra.models import CategoryModel, ProductModel

pytestmark = pytest.mark.integration


@pytest.fixture
async def session(migrated_database_url: str) -> AsyncIterator[AsyncSession]:
    engine = create_engine(migrated_database_url)
    async with create_session_factory(engine)() as db_session:
        yield db_session
        await db_session.rollback()
    await engine.dispose()


def product(sku: str = "RS-001", **overrides: object) -> ProductModel:
    values: dict[str, object] = {
        "sku": sku,
        "name": "Running Shoes",
        "price": Decimal("89.99"),
        "stock": 5,
    }
    return ProductModel(**(values | overrides))


async def flush_expecting(session: AsyncSession, constraint: str) -> None:
    with pytest.raises(IntegrityError) as raised:
        await session.flush()
    assert constraint in str(raised.value)


async def test_defaults_are_filled_by_the_database(session: AsyncSession) -> None:
    item = product()
    session.add(item)
    await session.flush()
    await session.refresh(item)

    assert item.id is not None
    assert item.version == 1
    assert item.created_at is not None
    assert item.updated_at is not None
    assert item.deleted_at is None
    assert item.category_id is None
    assert item.image_key is None
    assert item.weight_kg is None


async def test_optional_fields_round_trip_with_exact_decimals(session: AsyncSession) -> None:
    category = (
        await session.scalars(select(CategoryModel).where(CategoryModel.slug == "footwear"))
    ).one()
    category_id = category.id
    item = product(
        "RS-002",
        category_id=category_id,
        price=Decimal("0.00"),
        weight_kg=Decimal("0.350"),
        description="Lightweight",
        image_key="products/RS-002/a.webp",
    )
    session.add(item)
    await session.flush()
    session.expire_all()

    stored = (await session.scalars(select(ProductModel).where(ProductModel.sku == "RS-002"))).one()
    assert stored.price == Decimal("0.00")
    assert stored.weight_kg == Decimal("0.350")
    assert stored.category_id == category_id


async def test_price_keeps_two_decimals_and_rounds_extra_digits(session: AsyncSession) -> None:
    session.add(product("RS-003", price=Decimal("29.999")))
    await session.flush()

    result = await session.scalar(text("SELECT price FROM products WHERE sku = 'RS-003'"))

    assert result == Decimal("30.00")


async def test_price_beyond_twelve_digits_is_rejected(session: AsyncSession) -> None:
    session.add(product("RS-004", price=Decimal("10000000000.00")))

    with pytest.raises(DBAPIError):
        await session.flush()


async def test_negative_price_is_rejected(session: AsyncSession) -> None:
    session.add(product(price=Decimal("-0.01")))

    await flush_expecting(session, "ck_products_price_non_negative")


async def test_negative_stock_is_rejected(session: AsyncSession) -> None:
    session.add(product(stock=-1))

    await flush_expecting(session, "ck_products_stock_non_negative")


async def test_negative_weight_is_rejected(session: AsyncSession) -> None:
    session.add(product(weight_kg=Decimal("-1")))

    await flush_expecting(session, "ck_products_weight_non_negative")


async def test_version_below_one_is_rejected(session: AsyncSession) -> None:
    session.add(product(version=0))

    await flush_expecting(session, "ck_products_version_positive")


async def test_sku_is_unique(session: AsyncSession) -> None:
    session.add_all([product("DUP-1"), product("DUP-1", name="Other")])

    await flush_expecting(session, "uq_products_sku")


async def test_sku_stays_reserved_after_a_soft_delete(session: AsyncSession) -> None:
    session.add(product("GONE-1"))
    await session.flush()
    await session.execute(text("UPDATE products SET deleted_at = now() WHERE sku = 'GONE-1'"))
    session.add(product("GONE-1"))

    await flush_expecting(session, "uq_products_sku")


async def test_same_name_with_different_skus_is_allowed(session: AsyncSession) -> None:
    session.add_all([product("RS-010"), product("RS-050")])

    await session.flush()


async def test_unknown_category_is_rejected(session: AsyncSession) -> None:
    session.add(product(category_id="00000000-0000-4000-8000-0000000000ff"))

    await flush_expecting(session, "fk_products_category_id_categories")


async def test_a_category_in_use_cannot_be_deleted(session: AsyncSession) -> None:
    category = (
        await session.scalars(select(CategoryModel).where(CategoryModel.slug == "books"))
    ).one()
    session.add(product("BK-001", category_id=category.id))
    await session.flush()

    with pytest.raises(IntegrityError) as raised:
        await session.execute(text("DELETE FROM categories WHERE slug = 'books'"))
    assert "fk_products_category_id_categories" in str(raised.value)


@pytest.mark.parametrize("name", ["electronics", "ELECTRONICS", "ElEcTrOnIcS"])
async def test_category_names_are_unique_case_insensitively(
    session: AsyncSession, name: str
) -> None:
    session.add(CategoryModel(name=name, slug=f"{name.lower()}-copy"))

    await flush_expecting(session, "uq_categories_name_lower")


async def test_category_slug_is_unique(session: AsyncSession) -> None:
    session.add(CategoryModel(name="Brand New", slug="electronics"))

    await flush_expecting(session, "uq_categories_slug")


async def test_hostile_text_is_stored_literally(session: AsyncSession) -> None:
    hostile = "Robert'); DROP TABLE products;--"
    session.add(product("EVIL-1", name=hostile, description="<script>alert('xss')</script>"))
    await session.flush()
    session.expire_all()

    stored = (await session.scalars(select(ProductModel).where(ProductModel.sku == "EVIL-1"))).one()
    assert stored.name == hostile
    assert stored.description == "<script>alert('xss')</script>"
    assert await session.scalar(text("SELECT count(*) FROM products")) >= 1
