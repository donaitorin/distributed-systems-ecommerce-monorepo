from decimal import Decimal

import pytest
from cart_testing.support import SteppingClock, product

from cart.domain.cart import CartEntry, CartLine, CartView, Flag, FlagType, flags_for
from cart.domain.product import normalize_sku


def line(price: str = "89.99", quantity: int = 2) -> CartLine:
    started = CartLine.started(product(price=price), quantity, SteppingClock()())
    return started


def test_a_line_starts_from_the_product_snapshot() -> None:
    started = line()

    assert (started.sku, started.name, started.price, started.quantity) == (
        "RS-001",
        "Running Shoes",
        Decimal("89.99"),
        2,
    )
    assert started.total == Decimal("179.98")


def test_changing_the_quantity_keeps_the_snapshot_and_the_position() -> None:
    started = line()

    changed = started.with_quantity(5)

    assert (changed.quantity, changed.price, changed.added_at) == (
        5,
        started.price,
        started.added_at,
    )


def test_accepting_a_product_refreshes_price_name_and_image_only() -> None:
    started = line()

    refreshed = started.with_snapshot_of(product(price="70.00", name="Trail Shoes", image_key=None))

    assert (refreshed.price, refreshed.name, refreshed.image_key) == (
        Decimal("70.00"),
        "Trail Shoes",
        None,
    )
    assert (refreshed.quantity, refreshed.added_at) == (started.quantity, started.added_at)


def test_a_line_without_a_projected_product_has_no_flags() -> None:
    assert flags_for(line(), None) == ()


def test_an_unchanged_product_has_no_flags() -> None:
    assert flags_for(line(), product()) == ()


def test_a_different_price_is_flagged_with_both_prices() -> None:
    assert flags_for(line(), product(price="79.90")) == (
        Flag(FlagType.PRICE_CHANGED, old_price=Decimal("89.99"), new_price=Decimal("79.90")),
    )


def test_a_deleted_product_is_only_flagged_as_unavailable() -> None:
    flags = flags_for(line(), product(price="1.00", stock=0, deleted=True))

    assert flags == (Flag(FlagType.UNAVAILABLE),)


@pytest.mark.parametrize(("stock", "flagged"), [(2, False), (3, False), (1, True), (0, True)])
def test_a_quantity_above_the_stock_is_flagged_including_zero(stock: int, flagged: bool) -> None:
    flags = flags_for(line(quantity=2), product(stock=stock))

    assert flags == ((Flag(FlagType.INSUFFICIENT_STOCK, available=stock),) if flagged else ())


def test_price_and_stock_flags_can_be_combined() -> None:
    flags = flags_for(line(quantity=4), product(price="10.00", stock=1))

    assert [flag.type for flag in flags] == [FlagType.PRICE_CHANGED, FlagType.INSUFFICIENT_STOCK]


def test_the_view_counts_units_and_sums_the_saved_prices() -> None:
    entries = (CartEntry(line("10.00", 2), ()), CartEntry(line("5.50", 3), ()))

    view = CartView(entries)

    assert view.item_count == 5
    assert view.subtotal == Decimal("36.50")


def test_an_empty_view_has_a_zero_subtotal_with_cents() -> None:
    assert (CartView(()).item_count, str(CartView(()).subtotal)) == (0, "0.00")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(" rs-001 ", "RS-001"), ("A.b_c-9", "A.B_C-9"), ("", None), ("-X", None), ("a b", None)],
)
def test_skus_are_trimmed_and_uppercased(raw: str, expected: str | None) -> None:
    assert normalize_sku(raw) == expected
