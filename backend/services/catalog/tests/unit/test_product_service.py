from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from catalog_testing.support import SteppingClock

from catalog.application.errors import (
    DuplicateSkuError,
    PreconditionFailedError,
    ProductNotFoundError,
)
from catalog.application.products import ProductService, utc_now
from catalog.domain.errors import ValidationFailedError
from catalog.domain.preconditions import VersionPrecondition
from catalog.infra.memory import InMemoryStore, InMemoryUnitOfWork

ANY = VersionPrecondition(any_version=True)


@pytest.fixture
def service(store: InMemoryStore, clock: SteppingClock) -> ProductService:
    return ProductService(lambda: InMemoryUnitOfWork(store), clock)


def create_kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "sku": "rs-001",
        "name": "Running Shoes",
        "description": None,
        "category_id": None,
        "price": Decimal("89.99"),
        "stock": 10,
        "weight_kg": None,
    }
    return base | overrides


def replace_kwargs(**overrides: Any) -> dict[str, Any]:
    base = create_kwargs(name="Trail Shoes", price=Decimal("99.50"), stock=3)
    del base["sku"]
    return base | overrides


async def test_create_assigns_version_one_and_the_clock_time(
    service: ProductService, clock: SteppingClock
) -> None:
    product = await service.create(**create_kwargs())

    assert product.sku == "RS-001"
    assert product.version == 1
    assert product.created_at == product.updated_at == clock.now


async def test_create_attaches_the_category(service: ProductService, store: InMemoryStore) -> None:
    category = next(iter(store.categories.values()))

    product = await service.create(**create_kwargs(category_id=category.id))

    assert product.category == category


async def test_create_with_unknown_category_is_a_validation_error(service: ProductService) -> None:
    with pytest.raises(ValidationFailedError) as raised:
        await service.create(**create_kwargs(category_id=uuid4()))

    assert [item.location for item in raised.value.violations] == ["category_id"]


async def test_create_rejects_invalid_data_before_touching_storage(
    service: ProductService, store: InMemoryStore
) -> None:
    with pytest.raises(ValidationFailedError):
        await service.create(**create_kwargs(price=Decimal("-1")))

    assert store.products == {}


async def test_create_rejects_a_duplicate_sku_ignoring_case(service: ProductService) -> None:
    await service.create(**create_kwargs())

    with pytest.raises(DuplicateSkuError):
        await service.create(**create_kwargs(sku="RS-001", name="Other"))


async def test_a_deleted_sku_cannot_be_reused(service: ProductService) -> None:
    await service.create(**create_kwargs())
    await service.delete("RS-001", ANY)

    with pytest.raises(DuplicateSkuError):
        await service.create(**create_kwargs())


async def test_same_name_with_different_skus_is_allowed(service: ProductService) -> None:
    await service.create(**create_kwargs(sku="RS-001"))
    await service.create(**create_kwargs(sku="RS-050"))

    assert len(await service.list(10)) == 2


async def test_get_finds_a_product_by_any_casing(service: ProductService) -> None:
    await service.create(**create_kwargs())

    assert (await service.get(" rs-001 ")).sku == "RS-001"


@pytest.mark.parametrize("sku", ["MISSING", "not a sku!", ""])
async def test_get_unknown_or_malformed_sku_is_not_found(service: ProductService, sku: str) -> None:
    with pytest.raises(ProductNotFoundError):
        await service.get(sku)


async def test_list_is_ordered_by_sku_and_limited(service: ProductService) -> None:
    for sku in ("C-1", "A-1", "B-1"):
        await service.create(**create_kwargs(sku=sku))

    assert [item.sku for item in await service.list(10)] == ["A-1", "B-1", "C-1"]
    assert [item.sku for item in await service.list(2)] == ["A-1", "B-1"]


async def test_list_hides_deleted_products(service: ProductService) -> None:
    await service.create(**create_kwargs(sku="A-1"))
    await service.create(**create_kwargs(sku="B-1"))
    await service.delete("A-1", ANY)

    assert [item.sku for item in await service.list(10)] == ["B-1"]


async def test_replace_updates_every_field_and_bumps_the_version(
    service: ProductService, clock: SteppingClock
) -> None:
    created = await service.create(**create_kwargs(description="old"))
    clock.advance()

    updated = await service.replace(
        "rs-001",
        precondition=VersionPrecondition(versions=frozenset({1})),
        **replace_kwargs(),
    )

    assert updated.version == 2
    assert updated.name == "Trail Shoes"
    assert updated.description is None
    assert updated.price == Decimal("99.50")
    assert updated.stock == 3
    assert updated.id == created.id
    assert updated.created_at == created.created_at
    assert updated.updated_at == clock.now > created.updated_at


async def test_replace_with_a_stale_version_is_rejected_and_changes_nothing(
    service: ProductService,
) -> None:
    await service.create(**create_kwargs())
    await service.replace("RS-001", precondition=ANY, **replace_kwargs())

    with pytest.raises(PreconditionFailedError):
        await service.replace(
            "RS-001",
            precondition=VersionPrecondition(versions=frozenset({1})),
            **replace_kwargs(name="Lost update"),
        )

    current = await service.get("RS-001")
    assert current.name == "Trail Shoes"
    assert current.version == 2


async def test_replace_unknown_sku_is_not_found(service: ProductService) -> None:
    with pytest.raises(ProductNotFoundError):
        await service.replace("NOPE", precondition=ANY, **replace_kwargs())


async def test_replace_validates_before_checking_existence(service: ProductService) -> None:
    with pytest.raises(ValidationFailedError):
        await service.replace(
            "NOPE",
            precondition=ANY,
            **replace_kwargs(stock=-1),
        )


async def test_replace_with_unknown_category_is_rolled_back(
    service: ProductService, store: InMemoryStore
) -> None:
    await service.create(**create_kwargs())

    with pytest.raises(ValidationFailedError):
        await service.replace(
            "RS-001",
            precondition=ANY,
            **replace_kwargs(category_id=uuid4()),
        )

    assert (await service.get("RS-001")).version == 1


async def test_delete_hides_the_product_and_bumps_its_version(
    service: ProductService, store: InMemoryStore
) -> None:
    await service.create(**create_kwargs())

    await service.delete("RS-001", VersionPrecondition(versions=frozenset({1})))

    with pytest.raises(ProductNotFoundError):
        await service.get("RS-001")
    assert store.products["RS-001"].deleted_at is not None
    assert store.products["RS-001"].version == 2


async def test_delete_with_a_stale_version_is_rejected(service: ProductService) -> None:
    await service.create(**create_kwargs())

    with pytest.raises(PreconditionFailedError):
        await service.delete("RS-001", VersionPrecondition(versions=frozenset({7})))

    assert (await service.get("RS-001")).version == 1


async def test_delete_twice_is_not_found_the_second_time(service: ProductService) -> None:
    await service.create(**create_kwargs())
    await service.delete("RS-001", ANY)

    with pytest.raises(ProductNotFoundError):
        await service.delete("RS-001", ANY)


async def test_replace_and_delete_of_a_deleted_product_are_not_found(
    service: ProductService,
) -> None:
    await service.create(**create_kwargs())
    await service.delete("RS-001", ANY)

    with pytest.raises(ProductNotFoundError):
        await service.replace("RS-001", precondition=ANY, **replace_kwargs())


@pytest.mark.parametrize("sku", ["bad sku!", ""])
async def test_replace_and_delete_with_a_malformed_sku_are_not_found(
    service: ProductService, sku: str
) -> None:
    with pytest.raises(ProductNotFoundError):
        await service.replace(sku, precondition=ANY, **replace_kwargs())
    with pytest.raises(ProductNotFoundError):
        await service.delete(sku, ANY)


def test_default_clock_is_timezone_aware_utc() -> None:
    assert utc_now().utcoffset() is not None
