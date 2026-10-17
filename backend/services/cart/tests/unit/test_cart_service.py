from decimal import Decimal

import pytest
from cart_testing.support import FakeCatalog, SteppingClock, Stores, product

from cart.application.carts import CartService
from cart.application.errors import (
    CartFullError,
    CatalogUnavailableError,
    PriceChangedError,
    ProductNotFoundError,
)
from cart.domain.cart import MAX_LINES, FlagType

USER = "user-1"


@pytest.fixture
def service(stores: Stores, catalog: FakeCatalog, clock: SteppingClock) -> CartService:
    return CartService(stores.carts, stores.projection, catalog, clock)


async def test_an_empty_cart_has_no_lines_and_does_not_touch_the_projection(
    service: CartService,
) -> None:
    view = await service.view(USER)

    assert (view.entries, view.item_count, view.subtotal) == ((), 0, Decimal("0.00"))


async def test_adding_a_product_saves_the_catalog_snapshot_and_seeds_the_projection(
    service: CartService, stores: Stores, catalog: FakeCatalog
) -> None:
    view = await service.set_quantity(USER, "rs-001", 2, None)

    [entry] = view.entries
    assert (entry.line.sku, entry.line.quantity, entry.line.price) == (
        "RS-001",
        2,
        Decimal("89.99"),
    )
    assert entry.line.name == "Running Shoes"
    assert entry.flags == ()
    assert view.subtotal == Decimal("179.98")
    assert catalog.requests == ["RS-001"]
    assert stores.projection.entries["RS-001"] == product()


async def test_changing_the_quantity_of_a_known_line_does_not_call_the_catalog(
    service: CartService, catalog: FakeCatalog
) -> None:
    await service.set_quantity(USER, "RS-001", 1, None)
    catalog.requests.clear()
    catalog.unavailable = True

    view = await service.set_quantity(USER, "RS-001", 4, None)

    assert view.entries[0].line.quantity == 4
    assert catalog.requests == []


async def test_an_unknown_or_retired_product_is_not_found(service: CartService) -> None:
    with pytest.raises(ProductNotFoundError):
        await service.set_quantity(USER, "NOPE-1", 1, None)

    assert (await service.view(USER)).entries == ()


@pytest.mark.parametrize("sku", ["", "-bad", "a b", "x" * 80])
async def test_a_malformed_sku_is_not_found_without_calling_the_catalog(
    service: CartService, catalog: FakeCatalog, sku: str
) -> None:
    with pytest.raises(ProductNotFoundError):
        await service.set_quantity(USER, sku, 1, None)

    assert catalog.requests == []


async def test_an_unavailable_catalog_refuses_a_new_line_and_leaves_the_cart_alone(
    service: CartService, catalog: FakeCatalog
) -> None:
    catalog.unavailable = True

    with pytest.raises(CatalogUnavailableError):
        await service.set_quantity(USER, "RS-001", 1, None)

    assert (await service.view(USER)).entries == ()


async def test_the_cart_is_full_at_one_hundred_different_products(
    stores: Stores, clock: SteppingClock
) -> None:
    items = [product(sku=f"P-{number:03d}") for number in range(MAX_LINES + 1)]
    service = CartService(stores.carts, stores.projection, FakeCatalog(*items), clock)
    for item in items[:MAX_LINES]:
        await service.set_quantity(USER, item.sku, 1, None)

    with pytest.raises(CartFullError) as full:
        await service.set_quantity(USER, items[MAX_LINES].sku, 1, None)
    again = await service.set_quantity(USER, items[0].sku, 5, None)

    assert full.value.limit == MAX_LINES
    assert len(again.entries) == MAX_LINES
    assert again.entries[0].line.quantity == 5


async def test_lines_keep_the_order_in_which_they_were_added(
    stores: Stores, clock: SteppingClock
) -> None:
    catalog = FakeCatalog(product(sku="B-1"), product(sku="A-1"))
    service = CartService(stores.carts, stores.projection, catalog, clock)

    await service.set_quantity(USER, "B-1", 1, None)
    await service.set_quantity(USER, "A-1", 1, None)
    view = await service.set_quantity(USER, "B-1", 3, None)

    assert [entry.line.sku for entry in view.entries] == ["B-1", "A-1"]


async def test_carts_of_different_users_are_independent(service: CartService) -> None:
    await service.set_quantity("user-1", "RS-001", 1, None)

    assert (await service.view("user-2")).entries == ()


async def test_a_changed_price_is_flagged_but_the_line_keeps_its_snapshot(
    service: CartService, stores: Stores
) -> None:
    await service.set_quantity(USER, "RS-001", 2, None)
    await stores.projection.apply_state(product(price="79.90", version=2))

    view = await service.view(USER)

    [entry] = view.entries
    assert entry.line.price == Decimal("89.99")
    [flag] = entry.flags
    assert (flag.type, flag.old_price, flag.new_price) == (
        FlagType.PRICE_CHANGED,
        Decimal("89.99"),
        Decimal("79.90"),
    )
    assert view.subtotal == Decimal("179.98")


async def test_a_deleted_product_is_flagged_unavailable(
    service: CartService, stores: Stores
) -> None:
    await service.set_quantity(USER, "RS-001", 1, None)
    await stores.projection.apply_deletion("RS-001", 2)

    [entry] = (await service.view(USER)).entries

    assert [flag.type for flag in entry.flags] == [FlagType.UNAVAILABLE]


async def test_missing_stock_is_flagged_including_zero(
    service: CartService, stores: Stores
) -> None:
    await service.set_quantity(USER, "RS-001", 3, None)
    await stores.projection.apply_state(product(stock=0, version=2))

    [entry] = (await service.view(USER)).entries

    assert [(flag.type, flag.available) for flag in entry.flags] == [
        (FlagType.INSUFFICIENT_STOCK, 0)
    ]


async def test_accepting_the_new_price_refreshes_the_snapshot_and_keeps_the_quantity(
    service: CartService, catalog: FakeCatalog, stores: Stores
) -> None:
    await service.set_quantity(USER, "RS-001", 3, None)
    catalog.add(product(price="79.90", name="Running Shoes 2", version=2))

    view = await service.set_quantity(USER, "RS-001", 3, Decimal("79.90"))

    [entry] = view.entries
    assert (entry.line.price, entry.line.name, entry.line.quantity) == (
        Decimal("79.90"),
        "Running Shoes 2",
        3,
    )
    assert entry.flags == ()
    assert stores.projection.entries["RS-001"] == product(
        price="79.90", name="Running Shoes 2", version=2
    )


async def test_accepting_a_price_that_is_no_longer_the_current_one_is_a_conflict(
    service: CartService, catalog: FakeCatalog
) -> None:
    await service.set_quantity(USER, "RS-001", 1, None)
    catalog.add(product(price="60.00", version=3))

    with pytest.raises(PriceChangedError) as conflict:
        await service.set_quantity(USER, "RS-001", 1, Decimal("79.90"))

    assert conflict.value.current_price == Decimal("60.00")
    [entry] = (await service.view(USER)).entries
    assert entry.line.price == Decimal("89.99")


async def test_a_new_line_with_an_accepted_price_must_match_the_catalog(
    service: CartService,
) -> None:
    with pytest.raises(PriceChangedError):
        await service.set_quantity(USER, "RS-001", 1, Decimal("1.00"))

    view = await service.set_quantity(USER, "RS-001", 1, Decimal("89.99"))

    assert len(view.entries) == 1


async def test_accepting_a_price_for_a_retired_product_is_not_found(
    service: CartService, catalog: FakeCatalog
) -> None:
    await service.set_quantity(USER, "RS-001", 1, None)
    del catalog.products["RS-001"]

    with pytest.raises(ProductNotFoundError):
        await service.set_quantity(USER, "RS-001", 1, Decimal("89.99"))


async def test_removing_a_line_returns_the_rest_and_is_idempotent(
    stores: Stores, clock: SteppingClock
) -> None:
    catalog = FakeCatalog(product(sku="A-1"), product(sku="B-1"))
    service = CartService(stores.carts, stores.projection, catalog, clock)
    await service.set_quantity(USER, "A-1", 1, None)
    await service.set_quantity(USER, "B-1", 1, None)

    first = await service.remove(USER, "a-1")
    second = await service.remove(USER, "A-1")

    assert [entry.line.sku for entry in first.entries] == ["B-1"]
    assert second == first


async def test_removing_with_a_malformed_sku_is_not_found(service: CartService) -> None:
    with pytest.raises(ProductNotFoundError):
        await service.remove(USER, "??")


async def test_clearing_empties_the_cart(service: CartService) -> None:
    await service.set_quantity(USER, "RS-001", 1, None)

    await service.clear(USER)

    assert (await service.view(USER)).entries == ()
