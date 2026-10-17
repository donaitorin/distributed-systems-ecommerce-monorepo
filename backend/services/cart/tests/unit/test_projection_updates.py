from decimal import Decimal

from cart_testing.events import deleted_event, updated_event
from cart_testing.support import Stores, product

from cart.application.projection import ProjectionUpdates


async def reserved(stores: Stores, sku: str = "RS-001") -> ProjectionUpdates:
    await stores.projection.reserve(sku)
    return ProjectionUpdates(stores.projection)


async def test_an_update_fills_a_reserved_product(stores: Stores) -> None:
    updates = await reserved(stores)

    await updates.updated(updated_event(version=2, price="79.90", stock=5, image_key="k/1"))

    assert stores.projection.entries["RS-001"] == product(
        version=2, price="79.90", stock=5, image_key="k/1"
    )


async def test_an_update_for_a_product_in_no_cart_is_ignored(stores: Stores) -> None:
    updates = ProjectionUpdates(stores.projection)

    await updates.updated(updated_event(sku="OTHER-1"))
    await updates.deleted(deleted_event(sku="OTHER-1"))

    assert stores.projection.entries == {}


async def test_a_replayed_or_older_update_changes_nothing(stores: Stores) -> None:
    updates = await reserved(stores)
    await updates.updated(updated_event(version=3, price="30.00"))
    before = dict(stores.projection.entries)

    await updates.updated(updated_event(version=3, price="99.00"))
    await updates.updated(updated_event(version=2, price="20.00"))

    assert stores.projection.entries == before


async def test_a_deletion_flags_the_product_and_a_later_update_restores_it(
    stores: Stores,
) -> None:
    updates = await reserved(stores)
    await updates.updated(updated_event(version=2))

    await updates.deleted(deleted_event(version=3))
    assert stores.projection.entries["RS-001"] is not None
    assert stores.projection.entries["RS-001"].deleted is True

    await updates.updated(updated_event(version=4, price="10.00"))
    restored = stores.projection.entries["RS-001"]
    assert restored is not None
    assert (restored.deleted, restored.price) == (False, Decimal("10.00"))
